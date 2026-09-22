"""Finishing a turn that stopped to wait for a person.

A paused turn holds nothing in memory: the pause is a row in the approval table and the
work already done is in the message log. So resuming is just running the turn again with
no new user message, and what differs between these entry points is only how the waiting
row gets closed first.

Two ways to close one, and they are not interchangeable:

* `resolve_approval` decides a tool — it may run, or it may not.
* `answer_question` answers a question — the outcome is the text that came back.

Approving a question would close it with nothing in it, and the agent would resume having
learned nothing from a pause it took on purpose; answering a tool would let it run on the
strength of a sentence. Each refuses the other's rows.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from my_agent_crew.agent.events import Event
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.agent.turn_context import conversation_source
from my_agent_crew.store.approvals import PENDING
from my_agent_crew.store.models import IDLE, QUESTION


async def resolve_approval(
    deps: AgentDeps, conv_id: str, approval_id: str, approve: bool, always: bool = False
) -> AsyncIterator[Event]:
    """`always` approves and also lets this tool run without asking for the rest of the
    conversation; the ask list for shell commands still applies on top."""
    approval = deps.store.approvals.get(approval_id)
    if approval.conversation_id != conv_id or approval.status != PENDING:
        raise KeyError(approval_id)
    if approval.kind == QUESTION:
        raise KeyError(approval_id)  # answers come through `answer_question`
    deps.store.approvals.resolve(approval_id, approve)
    fields: dict[str, object] = {"status": IDLE}
    if approve and always:
        allowed = deps.store.get(conv_id).auto_approve
        if approval.tool_name not in allowed:
            fields["auto_approve"] = (*allowed, approval.tool_name)
    deps.store.update(conv_id, **fields)
    async for event in _resume(deps, conv_id):
        yield event


async def answer_question(
    deps: AgentDeps, conv_id: str, approval_id: str, answer: str
) -> AsyncIterator[Event]:
    """Close a waiting question with what the person said, then finish the turn."""
    approval = deps.store.approvals.get(approval_id)
    if approval.conversation_id != conv_id:
        raise KeyError(approval_id)
    deps.store.approvals.answer(approval_id, answer)  # raises unless pending and a question
    deps.store.update(conv_id, status=IDLE)
    async for event in _resume(deps, conv_id):
        yield event


async def _resume(deps: AgentDeps, conv_id: str) -> AsyncIterator[Event]:
    """Carry on under the source that first started the turn: an approval arriving from
    the web does not make a job's turn a web turn."""
    source = conversation_source(deps.store, conv_id)
    async for event in run_turn(deps, conv_id, None, source=source):
        yield event
