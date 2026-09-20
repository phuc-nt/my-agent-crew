"""Carrying out the tool calls the model asked for, before the next completion.

A call the agent may not make on its own stops the turn: an approval is recorded and the
turn ends, to be resumed by `resolve_approval` once the person decides. Everything else
runs and its result is appended, so the next completion sees what happened.
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
from my_agent_crew.store.approvals import DENIED, EXPIRED, PENDING
from my_agent_crew.store.models import AWAITING_APPROVAL, Conversation
from my_agent_crew.texts import DENIED_TOOL, EXPIRED_TOOL, SHELL_ASK_REASON
from my_agent_crew.tools.registry import ToolResult
from my_agent_crew.tools.shell import SHELL_TOOL_NAME, ask_reason

if TYPE_CHECKING:  # the loop owns the deps; importing it back would be a cycle
    from my_agent_crew.agent.loop import AgentDeps

REFUSALS = {DENIED: DENIED_TOOL, EXPIRED: EXPIRED_TOOL}


def _ask_reason(deps: AgentDeps, name: str, arguments: dict[str, Any]) -> str | None:
    """A shell command whose shape is on the ask list is approved even when the
    conversation is autonomous; every other call keeps the old rule."""
    if name != SHELL_TOOL_NAME:
        return None
    return ask_reason(str(arguments.get("command", "")), deps.settings.shell_ask_patterns)


def needs_decision(conv: Conversation, name: str, reason: str | None) -> bool:
    """An autonomous conversation and a tool the person said to always allow both skip
    the pause; a command on the ask list pauses regardless, that guard is additive."""
    if reason:
        return True
    return not conv.autonomous and name not in conv.auto_approve


def _pauses_for_a_person(deps: AgentDeps, conv: Conversation, call: ToolCall) -> bool:
    tool = deps.tools.get(call.name)
    if tool is None or not tool.requires_approval:
        return False
    return needs_decision(conv, call.name, _ask_reason(deps, call.name, call.arguments))


async def _execute(deps: AgentDeps, call: ToolCall) -> ToolResult:
    """Each call runs with its own id in context. `asyncio.gather` copies the context per
    task, so a batched call reads its own id and not whichever one was set last."""
    set_tool_call_id(call.id)
    return await deps.tools.execute(call.name, call.arguments)


async def _record(deps: AgentDeps, conv_id: str, call: ToolCall, result: ToolResult) -> Event:
    deps.store.append(
        conv_id,
        Message(role="tool", content=result.output, tool_call_id=call.id, name=call.name),
    )
    return ToolResultEvent(tool_call_id=call.id, name=call.name, ok=result.ok, output=result.output)


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
            approval = deps.store.approvals.find_for_call(conv_id, call.id)
            if approval is None:
                approval = deps.store.approvals.create(
                    conv_id, last.id, call, ttl_seconds=deps.settings.approval_ttl_seconds
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
                )
                return
            if approval.status in REFUSALS:
                refusal = REFUSALS[approval.status]
                yield await _record(deps, conv_id, call, ToolResult(ok=False, output=refusal))
                continue
        yield ToolCallEvent(tool_call_id=call.id, name=call.name, arguments=call.arguments)
        result = await _execute(deps, call)
        yield await _record(deps, conv_id, call, result)
