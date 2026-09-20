"""Carrying out the tool calls the model asked for, before the next completion.

A call the agent may not make on its own stops the turn: an approval is recorded and the
turn ends, to be resumed by `resolve_approval` once the person decides. Everything else
runs and its result is appended, so the next completion sees what happened.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    Event,
    ToolCallEvent,
    ToolResultEvent,
)
from my_agent_crew.llm.types import Message
from my_agent_crew.store.approvals import DENIED, PENDING
from my_agent_crew.store.models import AWAITING_APPROVAL
from my_agent_crew.texts import DENIED_TOOL, SHELL_ASK_REASON
from my_agent_crew.tools.shell import SHELL_TOOL_NAME, ask_reason

if TYPE_CHECKING:  # the loop owns the deps; importing it back would be a cycle
    from my_agent_crew.agent.loop import AgentDeps


def _ask_reason(deps: AgentDeps, name: str, arguments: dict[str, Any]) -> str | None:
    """A shell command whose shape is on the ask list is approved even when the
    conversation is autonomous; every other call keeps the old rule."""
    if name != SHELL_TOOL_NAME:
        return None
    return ask_reason(str(arguments.get("command", "")), deps.settings.shell_ask_patterns)


async def settle_tool_calls(deps: AgentDeps, conv_id: str) -> AsyncIterator[Event]:
    history = deps.store.history(conv_id)
    assistants = [m for m in history if m.message.role == "assistant"]
    if not assistants or not assistants[-1].message.tool_calls:
        return
    last = assistants[-1]
    answered = {m.message.tool_call_id for m in history if m.seq > last.seq}
    conv = deps.store.get(conv_id)
    for call in last.message.tool_calls:
        if call.id in answered:
            continue
        tool = deps.tools.get(call.name)
        reason = _ask_reason(deps, call.name, call.arguments)
        if tool is not None and tool.requires_approval and (not conv.autonomous or reason):
            approval = deps.store.approvals.find_for_call(conv_id, call.id)
            if approval is None:
                approval = deps.store.approvals.create(conv_id, last.id, call)
                deps.store.update(conv_id, status=AWAITING_APPROVAL)
            if approval.status == PENDING:
                yield ApprovalRequiredEvent(
                    approval_id=approval.id,
                    tool_call_id=call.id,
                    name=call.name,
                    arguments=call.arguments,
                    reason=SHELL_ASK_REASON.format(pattern=reason) if reason else "",
                )
                return
            if approval.status == DENIED:
                deps.store.append(
                    conv_id,
                    Message(role="tool", content=DENIED_TOOL, tool_call_id=call.id, name=call.name),
                )
                yield ToolResultEvent(
                    tool_call_id=call.id, name=call.name, ok=False, output=DENIED_TOOL
                )
                continue
        yield ToolCallEvent(tool_call_id=call.id, name=call.name, arguments=call.arguments)
        result = await deps.tools.execute(call.name, call.arguments)
        deps.store.append(
            conv_id,
            Message(role="tool", content=result.output, tool_call_id=call.id, name=call.name),
        )
        yield ToolResultEvent(
            tool_call_id=call.id, name=call.name, ok=result.ok, output=result.output
        )
