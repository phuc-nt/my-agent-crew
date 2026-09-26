"""Carrying out the tool calls the model asked for, before the next completion.

A call the agent may not make on its own stops the turn: an approval is recorded and the
turn ends, to be resumed from `agent.resume` once the person decides. Everything else
runs and its result is appended, so the next completion sees what happened.

A question the agent asked with `ask_user` pauses the same way and is resumed the same
way, but it closes with the person's words rather than a yes or no, and running out of
time hands it a default instead of a refusal. Which calls pause is `tool_gate`'s call.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from my_agent_crew.agent.delegate_relay import relay_reply
from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    Event,
    ToolCallEvent,
    ToolResultEvent,
)
from my_agent_crew.agent.tool_batches import split_batches
from my_agent_crew.agent.tool_gate import ask_reason_for, pauses_for_a_person
from my_agent_crew.agent.turn_context import set_tool_call_id
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store.approvals import ANSWERED, DENIED, EXPIRED, PENDING
from my_agent_crew.store.models import AWAITING_APPROVAL, QUESTION, TOOL
from my_agent_crew.texts import DENIED_TOOL, EXPIRED_TOOL, SHELL_ASK_REASON
from my_agent_crew.tools.ask_user import (
    ASK_USER_TOOL_NAME,
    answer_result,
    options_of,
    unanswered_result,
)
from my_agent_crew.tools.registry import ToolResult

if TYPE_CHECKING:  # the loop owns the deps; importing it back would be a cycle
    from my_agent_crew.agent.loop import AgentDeps

REFUSALS = {DENIED: DENIED_TOOL, EXPIRED: EXPIRED_TOOL}


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
    batches = split_batches(pending, deps.tools, lambda c: not pauses_for_a_person(deps, conv, c))
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
        if pauses_for_a_person(deps, conv, call):
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
                reason = ask_reason_for(deps, call.name, call.arguments)
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
        # A finished delegation that was the whole turn ends it in the child's words.
        async for event in relay_reply(deps, conv_id, call, result):
            yield event
