"""Which tool calls a restart cut may be made again, and the turn that carries on after one.

A call with no result when the server stopped may or may not have run. One that only reads
is simply made again. One that changes something is closed with a note saying so, and the
model decides what to do once it has looked: made twice unseen, it could write, send or pay
twice. A call that never got as far as running — it waits on a person, was refused, or could
not be run at all — is left to the turn, which settles it as it always does.

A tool says which kind it is with `Tool.replay_safe`, and one that says nothing is taken to
change something.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from my_agent_crew.agent.approval_lookup import matches
from my_agent_crew.agent.events import Event
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.tool_calls import REFUSALS, refuse_unanswered
from my_agent_crew.agent.tool_gate import pauses_for_a_person
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store.approvals import PENDING
from my_agent_crew.store.models import QUESTION, Conversation
from my_agent_crew.texts import RESTART_CUT_TOOL

if TYPE_CHECKING:
    from my_agent_crew.agent.loop import AgentDeps


def replayable(deps: AgentDeps, conv: Conversation, call: ToolCall) -> bool:
    """Whether the turn may settle this unanswered call itself: it never ran, or running
    it again changes nothing."""
    tool = None if call.invalid else deps.tools.get(call.name)
    if tool is None:
        return True  # answered without being run: no such tool, or arguments that never parsed
    approval = deps.store.approvals.find_for_call(conv.id, call.id)
    if approval is None:
        # Nobody was asked. Either it still has to ask, so it never ran, or it runs unasked.
        return pauses_for_a_person(deps, conv, call) or tool.replay_safe
    if approval.status == PENDING or approval.kind == QUESTION:
        return True  # still waits, or closes with what the person said
    if approval.status in REFUSALS or not matches(approval, call):
        return True  # refused, which is its result
    return tool.replay_safe  # allowed, so it may have run


async def continue_cut_turn(deps: AgentDeps, conv_id: str, source: str) -> AsyncIterator[Event]:
    """The rest of a turn a restart cut. The calls that may not be repeated are closed
    first; then the turn carries on from the log, as one resumed after a decision does."""
    conv = deps.store.get(conv_id)
    async for event in refuse_unanswered(
        deps, conv_id, RESTART_CUT_TOOL, only=lambda call: not replayable(deps, conv, call)
    ):
        yield event
    async for event in run_turn(deps, conv_id, None, source=source):
        yield event
