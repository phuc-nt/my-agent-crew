"""Carrying out the tool calls the model asked for, before the next completion.

A call the agent may not make on its own stops the turn: an approval is recorded and the
turn ends, to be resumed from `agent.resume` once the person decides. Everything else
runs and its result is appended, so the next completion sees what happened.

A question the agent asked with `ask_user` pauses the same way and is resumed the same
way, but it closes with the person's words rather than a yes or no, and running out of
time hands it a default instead of a refusal.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    Event,
    ToolCallEvent,
    ToolResultEvent,
)
from my_agent_crew.agent.tool_batches import split_batches
from my_agent_crew.agent.turn_context import set_tool_call_id
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store.approvals import ANSWERED, DENIED, EXPIRED, PENDING
from my_agent_crew.store.models import AWAITING_APPROVAL, QUESTION, TOOL, Conversation
from my_agent_crew.texts import DENIED_TOOL, EXPIRED_TOOL, SHELL_ASK_REASON
from my_agent_crew.tools.ask_user import (
    ASK_USER_TOOL_NAME,
    answer_result,
    options_of,
    unanswered_result,
)
from my_agent_crew.tools.registry import ToolResult
from my_agent_crew.tools.shell import SHELL_TOOL_NAME, ask_reason, deny_reason
from my_agent_crew.tools.shell_temp_paths import deletes_only_temp_paths

if TYPE_CHECKING:  # the loop owns the deps; importing it back would be a cycle
    from my_agent_crew.agent.loop import AgentDeps

REFUSALS = {DENIED: DENIED_TOOL, EXPIRED: EXPIRED_TOOL}


def _ask_reason(deps: AgentDeps, name: str, arguments: dict[str, Any]) -> str | None:
    """A shell command whose shape is on the ask list is approved even when the
    conversation is autonomous; every other call keeps the old rule.

    One shape is let through: an agent deleting a temp directory it made itself. That
    tripped the list on every cleanup and stalled unattended runs, while deleting nothing
    of the person's. The exemption only holds when every path the command names resolves
    inside a system temp root — see `deletes_only_temp_paths`.
    """
    if name != SHELL_TOOL_NAME:
        return None
    command = str(arguments.get("command", ""))
    reason = ask_reason(command, deps.settings.shell_ask_patterns)
    if reason and deletes_only_temp_paths(command):
        return None
    return reason


def needs_decision(
    conv: Conversation, name: str, reason: str | None, allowed: bool = False
) -> bool:
    """Whether this call stops the turn to ask a person, in strict order:

    1. A question never skips. Autonomy means "do not ask me to authorise your tools",
       not "never speak to me"; a question that approved itself would be answered by
       nobody and tell the agent nothing.
    2. A command matching the ask list pauses regardless. That guard is additive, and it
       sits above the allow list on purpose: a person who names `rm -rf` as dangerous and
       `git` as routine means `git reset --hard` to ask, not to run.
    3. A command matching the allow list runs, autonomous or not. This is the point of
       the list — it lets a supervised agent get on with the routine parts of its job.
    4. Otherwise the old rule: autonomy, or a tool the person said to always allow.
    """
    if name == ASK_USER_TOOL_NAME:
        return True
    if reason:
        return True
    if allowed:
        return False
    return not conv.autonomous and name not in conv.auto_approve


def _allowed(deps: AgentDeps, name: str, arguments: dict[str, Any]) -> bool:
    """A shell command whose shape the person marked routine. Only shell: every other
    tool is allowed per tool, through `auto_approve`, not per argument."""
    if name != SHELL_TOOL_NAME:
        return False
    command = str(arguments.get("command", ""))
    return ask_reason(command, deps.settings.shell_allow_patterns) is not None


def _pauses_for_a_person(deps: AgentDeps, conv: Conversation, call: ToolCall) -> bool:
    tool = deps.tools.get(call.name)
    denied = deny_reason(call.arguments, deps.settings.shell_deny_patterns)
    if tool is None or not tool.requires_approval or (call.name == SHELL_TOOL_NAME and denied):
        return False
    return needs_decision(
        conv,
        call.name,
        _ask_reason(deps, call.name, call.arguments),
        _allowed(deps, call.name, call.arguments),
    )


async def _execute(deps: AgentDeps, call: ToolCall) -> ToolResult:
    """Each call runs with its own id in context. `asyncio.gather` copies the context per
    task, so a batched call reads its own id and not whichever one was set last."""
    set_tool_call_id(call.id)
    return await deps.tools.execute(call.name, call.arguments)


async def _record(deps: AgentDeps, conv_id: str, call: ToolCall, result: ToolResult) -> Event:
    if result.metered:  # a tool that paid a model is charged like a completion
        deps.store.add_spend(conv_id, result.cost_usd)
    deps.store.append(
        conv_id,
        Message(role="tool", content=result.output, tool_call_id=call.id, name=call.name),
    )
    return ToolResultEvent(
        tool_call_id=call.id,
        name=call.name,
        ok=result.ok,
        output=result.output,
        shaped_kind=result.shaped_kind,
        original_chars=result.original_chars,
    )


async def settle_tool_calls(deps: AgentDeps, conv_id: str) -> AsyncIterator[Event]:
    history = deps.store.history(conv_id)
    assistants = [m for m in history if m.message.role == "assistant"]
    if not assistants or not assistants[-1].message.tool_calls:
        return
    last = assistants[-1]
    answered = {m.message.tool_call_id for m in history if m.seq > last.seq}
    conv = deps.store.get(conv_id)
    pending = [c for c in last.message.tool_calls if c.id not in answered]
    batches = split_batches(pending, deps.tools, lambda c: not _pauses_for_a_person(deps, conv, c))
    for batch in batches:
        if len(batch) > 1:
            for call in batch:
                yield ToolCallEvent(tool_call_id=call.id, name=call.name, arguments=call.arguments)
            results = await asyncio.gather(*(_execute(deps, c) for c in batch))
            # Written back in call order, not completion order, so the history a resumed
            # turn reads is the same whichever task finished first.
            for call, result in zip(batch, results, strict=True):
                yield await _record(deps, conv_id, call, result)
            continue
        call = batch[0]
        if _pauses_for_a_person(deps, conv, call):
            asking = call.name == ASK_USER_TOOL_NAME
            approval = deps.store.approvals.find_for_call(conv_id, call.id)
            if approval is None:
                approval = deps.store.approvals.create(
                    conv_id,
                    last.id,
                    call,
                    ttl_seconds=deps.settings.approval_ttl_seconds,
                    kind=QUESTION if asking else TOOL,
                    options=options_of(call.arguments) if asking else [],
                )
                deps.store.update(conv_id, status=AWAITING_APPROVAL)
            if approval.status == PENDING:
                reason = _ask_reason(deps, call.name, call.arguments)
                yield ApprovalRequiredEvent(
                    approval_id=approval.id,
                    tool_call_id=call.id,
                    name=call.name,
                    arguments=call.arguments,
                    reason=SHELL_ASK_REASON.format(pattern=reason) if reason else "",
                    expires_at=approval.expires_at or "",
                    kind=approval.kind,
                    options=list(approval.options),
                )
                return
            if approval.kind == QUESTION:
                # An answered question hands over the person's words; an expired one hands
                # over its default. Neither is a refusal: the turn carries on either way.
                answered = approval.status == ANSWERED and approval.answer is not None
                output = (
                    answer_result(approval.answer)
                    if answered
                    else unanswered_result(call.arguments)
                )
                yield ToolCallEvent(tool_call_id=call.id, name=call.name, arguments=call.arguments)
                yield await _record(deps, conv_id, call, ToolResult(ok=True, output=output))
                continue
            if approval.status in REFUSALS:
                refusal = REFUSALS[approval.status]
                yield await _record(deps, conv_id, call, ToolResult(ok=False, output=refusal))
                continue
        yield ToolCallEvent(tool_call_id=call.id, name=call.name, arguments=call.arguments)
        result = await _execute(deps, call)
        yield await _record(deps, conv_id, call, result)
