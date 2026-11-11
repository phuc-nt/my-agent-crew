"""A call a person refused is not put to them twice in one turn: the same tool with the
same arguments, asked again after a denial or an expiry, is refused in code. Nothing is
ever approved this way, another call still asks, and so does the next turn."""

from __future__ import annotations

import asyncio
from datetime import datetime

from my_agent_crew.agent.approval_expiry import expire_overdue
from my_agent_crew.agent.events import ApprovalRequiredEvent, DoneEvent, ToolResultEvent
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store.approvals import APPROVED, DENIED, EXPIRED
from my_agent_crew.store.models import IDLE
from my_agent_crew.texts import DENIED_TOOL, EXPIRED_TOOL
from my_agent_crew.texts_approval import DECIDED_VIA, DENIED_NOTE, REPEATED_REFUSAL
from tests.conftest import collect
from tests.queue_helpers import Rig

FIRST = ToolCall("c1", "guarded", {"path": "a.txt", "mode": "w"})
SAME = ToolCall("c2", "guarded", {"mode": "w", "path": "a.txt"})  # the keys in another order
OTHER = ToolCall("c3", "guarded", {"path": "b.txt", "mode": "w"})
SLOW = ToolCall("c4", "slow", {})
DENIED_ON_WEB = f"{DENIED_TOOL} {DENIED_NOTE.format(via=DECIDED_VIA['chat'])}"


async def paused(rig: Rig, conv_id: str | None = None, text: str = "làm đi"):
    events = await collect(rig.inbound.stream(conv_id or rig.conv.id, text))
    assert isinstance(events[-1], ApprovalRequiredEvent)
    return events[-1]


async def decided(rig: Rig, request, approve: bool, conv_id: str | None = None) -> list:
    conv_id = conv_id or rig.conv.id
    return await collect(rig.inbound.decide(conv_id, request.approval_id, approve))


def requests_of(rig: Rig, conv_id: str | None = None) -> list[tuple[str, str]]:
    """Every request the conversation ever opened, oldest first: its call and how it ended."""
    conv_id = conv_id or rig.conv.id
    settled = rig.store.approvals.recent(conversation_id=conv_id)[::-1]
    waiting = [a for a in rig.store.approvals.waiting() if a.conversation_id == conv_id]
    return [(a.tool_call_id, a.status) for a in [*settled, *waiting]]


async def test_the_same_call_after_a_denial_is_refused_without_asking_again(rigs):
    rig = rigs([completion(tool_calls=[FIRST]), completion(tool_calls=[SAME]), completion("thôi")])
    events = await decided(rig, await paused(rig), approve=False)
    assert not [e for e in events if isinstance(e, ApprovalRequiredEvent)]
    results = [(e.tool_call_id, e.ok, e.output) for e in events if isinstance(e, ToolResultEvent)]
    assert results == [("c1", False, DENIED_ON_WEB), ("c2", False, REPEATED_REFUSAL)]
    assert isinstance(events[-1], DoneEvent)
    assert requests_of(rig) == [("c1", DENIED)]  # no second request was opened
    assert rig.store.approvals.waiting() == [] and rig.store.get(rig.conv.id).status == IDLE
    assert rig.statuses() == ["done"] and rig.guarded.runs == 0
    told = rig.provider.requests[2].messages[-1]
    assert (told.role, told.content) == ("tool", REPEATED_REFUSAL)


async def test_the_same_call_after_an_expiry_is_refused_without_asking_again(rigs):
    rig = rigs([completion(tool_calls=[FIRST]), completion(tool_calls=[SAME]), completion("thôi")])
    request = await paused(rig)
    deadline = datetime.fromisoformat(request.expires_at)
    closed = await expire_overdue({rig.deps.agent.id: rig.deps}, rig.hub, now=deadline)
    assert closed == [request.approval_id]
    assert requests_of(rig) == [("c1", EXPIRED)]
    assert rig.history()[-4:] == [
        ("tool", EXPIRED_TOOL),
        ("assistant", ""),
        ("tool", REPEATED_REFUSAL),
        ("assistant", "thôi"),
    ]
    assert rig.statuses() == ["done"] and rig.guarded.runs == 0


async def test_two_identical_calls_in_one_message_are_asked_once(rigs):
    rig = rigs([completion(tool_calls=[FIRST, SAME]), completion("thôi")])
    events = await decided(rig, await paused(rig), approve=False)
    outputs = [e.output for e in events if isinstance(e, ToolResultEvent)]
    assert outputs == [DENIED_ON_WEB, REPEATED_REFUSAL]
    assert requests_of(rig) == [("c1", DENIED)]


async def test_a_call_with_other_arguments_still_asks(rigs):
    rig = rigs([completion(tool_calls=[FIRST]), completion(tool_calls=[OTHER]), completion("ok")])
    events = await decided(rig, await paused(rig), approve=False)
    assert isinstance(events[-1], ApprovalRequiredEvent) and events[-1].tool_call_id == "c3"
    assert requests_of(rig) == [("c1", DENIED), ("c3", "pending")]


async def test_the_next_turn_asks_again(rigs):
    rig = rigs([completion(tool_calls=[FIRST]), completion("thôi"), completion(tool_calls=[SAME])])
    await decided(rig, await paused(rig), approve=False)
    again = await paused(rig, text="tôi đổi ý, làm đi")
    assert again.tool_call_id == "c2"
    assert requests_of(rig) == [("c1", DENIED), ("c2", "pending")]


async def test_an_approved_call_made_again_asks_again_and_is_never_let_through(rigs):
    rig = rigs([completion(tool_calls=[FIRST]), completion(tool_calls=[SAME]), completion("ok")])
    events = await decided(rig, await paused(rig), approve=True)
    assert isinstance(events[-1], ApprovalRequiredEvent) and events[-1].tool_call_id == "c2"
    assert requests_of(rig) == [("c1", APPROVED), ("c2", "pending")] and rig.guarded.runs == 1


async def test_a_steer_after_the_refusal_lets_the_same_call_ask_again(rigs):
    """What the person says mid-turn may be a change of mind, as a new message would be."""
    script = [completion(tool_calls=[FIRST]), completion(tool_calls=[SLOW])]
    rig = rigs([*script, completion(tool_calls=[SAME])])
    request = await paused(rig)
    resumed = asyncio.create_task(decided(rig, request, approve=False))
    await asyncio.wait_for(rig.slow.started.wait(), 2)
    await collect(rig.inbound.stream(rig.conv.id, "/steer cứ làm đi"))
    rig.slow.release.set()
    events = await asyncio.wait_for(resumed, 2)
    assert isinstance(events[-1], ApprovalRequiredEvent) and events[-1].tool_call_id == "c2"


async def test_a_delegated_child_is_held_to_the_same_rule(rigs):
    rig = rigs([completion(tool_calls=[FIRST]), completion(tool_calls=[SAME]), completion("thôi")])
    child = rig.store.create("Việc con", agent_id=rig.deps.agent.id, parent_call_id="call-1")
    events = await decided(rig, await paused(rig, child.id), approve=False, conv_id=child.id)
    outputs = [e.output for e in events if isinstance(e, ToolResultEvent)]
    assert outputs == [DENIED_ON_WEB, REPEATED_REFUSAL]
    assert requests_of(rig, child.id) == [("c1", DENIED)]
