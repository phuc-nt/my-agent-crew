"""A finished delegation that was the whole turn is answered in the child's words.

The delegator's next model call would only retell what the child said: one more round
trip, and one more chance to drop a number or a `FILE:` line on the way. So when the turn
since the person's message was exactly one `delegate` call, and the child finished, the
child's answer is stored as the delegator's reply as it stands and the turn ends there.

Everything else still goes back through the delegator, which is the agent that knows how
to ask the person: a child that stopped short (no `reply` rides on its result), one that
answered nothing, one that came back BLOCKED, a call made with `relay: false`, or a turn
that also read a file, wrote a note or delegated twice."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING

from my_agent_crew import texts
from my_agent_crew.agent.events import AssistantMessageEvent, Event
from my_agent_crew.agents.roster import DELEGATE_TOOL_NAME
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store import StoredMessage
from my_agent_crew.tools.progress_note import PROGRESS_NOTE_TOOL_NAME
from my_agent_crew.tools.registry import ToolResult

if TYPE_CHECKING:
    from my_agent_crew.agent.loop import AgentDeps

# A child that needs the person's decision writes this word; its answer is for the
# delegator to act on, not for the person to read as a result.
BLOCKED_MARK = "BLOCKED"


def relayable(result: ToolResult) -> str | None:
    """The answer to hand on, or None when the result must go back through the model."""
    if not result.ok or result.reply is None:
        return None
    answer = result.reply.strip()
    if not answer or answer == texts.EMPTY_REPLY or BLOCKED_MARK in answer:
        return None
    return answer


def turn_was_one_delegation(history: Sequence[StoredMessage], call_id: str) -> bool:
    """Since the person last spoke, the only tool call was this delegation. Progress
    notes do not count: they are the agent narrating, not the agent working."""
    calls: list[ToolCall] = []
    for stored in reversed(history):
        if stored.message.role == "user":
            break
        if stored.message.role == "assistant":
            calls.extend(stored.message.tool_calls)
    work = [c for c in calls if c.name != PROGRESS_NOTE_TOOL_NAME]
    return len(work) == 1 and work[0].id == call_id and work[0].name == DELEGATE_TOOL_NAME


async def relay_reply(
    deps: AgentDeps, conv_id: str, call: ToolCall, result: ToolResult
) -> AsyncIterator[Event]:
    """Stores the child's answer as this conversation's reply when it may stand as one.
    No provider or model is named on it because none spoke; the run timeline and the
    usage stats read that as "no model call", which is the point."""
    answer = relayable(result)
    if answer is None or not turn_was_one_delegation(deps.store.history(conv_id), call.id):
        return
    stored = deps.store.append(conv_id, Message(role="assistant", content=answer))
    yield AssistantMessageEvent(
        message_id=stored.id,
        content=answer,
        tool_calls=[],
        provider=None,
        model=None,
        cost_usd=0.0,
    )
