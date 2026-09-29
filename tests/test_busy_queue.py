"""A message that finds its conversation busy waits in the conversation's queue and is
answered by a turn of its own once the running one is over. A conversation waiting on a
person's decision refuses new messages instead, and a decision holds the conversation from
the moment it is taken, so nothing races the turn it resumes."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from my_agent_crew import texts
from my_agent_crew.agent.approval_expiry import expire_overdue
from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    AssistantMessageEvent,
    DoneEvent,
    QueuedEvent,
)
from my_agent_crew.agents.kit_commands import EmptySteer
from my_agent_crew.inbound import Inbound, InboundBusy
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store.approvals import EXPIRED, PENDING
from my_agent_crew.store.queue import FOLLOW_UP, QUEUE_LIMIT, QueueFull
from my_agent_crew.tools.ask_user import ASK_USER_TOOL_NAME, answer_result
from tests.conftest import collect
from tests.queue_helpers import Rig, settle_loop, until, while_the_tool_runs

SLOW = ToolCall("c1", "slow", {})
GUARDED = ToolCall("g1", "guarded", {})
ASK = ToolCall("q1", ASK_USER_TOOL_NAME, {"question": "A hay B?", "options": ["A", "B"]})


async def paused(rig: Rig, text: str = "làm đi") -> ApprovalRequiredEvent:
    """Runs a turn up to the point where it waits for a person; returns what it asks."""
    *_, pause = await collect(rig.inbound.stream(rig.conv.id, text))
    assert isinstance(pause, ApprovalRequiredEvent)
    return pause


async def test_a_message_sent_while_a_turn_runs_waits_and_gets_a_turn_of_its_own(rigs):
    rig = rigs(
        [completion(tool_calls=[SLOW]), completion("xong việc 1"), completion("trả lời tin 2")]
    )
    first = asyncio.create_task(collect(rig.inbound.stream(rig.conv.id, "việc 1")))
    await asyncio.wait_for(rig.slow.started.wait(), 2)
    [queued] = await collect(rig.inbound.stream(rig.conv.id, "tin 2"))
    assert queued == QueuedEvent(item_id=queued.item_id, kind=FOLLOW_UP, position=1)
    assert rig.statuses() == ["running"]
    assert [item.to_dict() for item in rig.store.queue.peek_all(rig.conv.id)] == [
        {"id": queued.item_id, "kind": FOLLOW_UP, "text": "tin 2"}
    ]
    rig.slow.release.set()
    events = await asyncio.wait_for(first, 2)
    # The running turn went on as if nothing had been said...
    answers = [e.content for e in events if isinstance(e, AssistantMessageEvent)]
    assert answers == ["", "xong việc 1"] and isinstance(events[-1], DoneEvent)
    # ...and once it was over, the message was answered by a turn of its own.
    await until(lambda: rig.statuses() == ["done", "done"])
    assert rig.history()[-3:] == [
        ("assistant", "xong việc 1"),
        ("user", "tin 2"),
        ("assistant", "trả lời tin 2"),
    ]
    assert rig.runs()[1].source == "chat" and rig.store.queue.count(rig.conv.id) == 0


async def test_messages_that_waited_together_are_answered_together_as_written(rigs):
    rig = rigs([completion(tool_calls=[SLOW]), completion("xong"), completion("đã đọc cả ba")])
    answers, _ = await while_the_tool_runs(rig, "a", "/tmp/x", "/nope y")
    # A path or a command the agent does not know is a message like any other.
    assert [(a.kind, a.position) for [a] in answers] == [(FOLLOW_UP, n) for n in (1, 2, 3)]
    await until(lambda: rig.statuses() == ["done", "done"])
    assert rig.provider.requests[2].messages[-1].content == "a\n\n/tmp/x\n\n/nope y"
    assert rig.history()[-2:] == [
        ("user", "a\n\n/tmp/x\n\n/nope y"),
        ("assistant", "đã đọc cả ba"),
    ]


async def test_a_bare_steer_is_refused_whether_or_not_a_turn_runs(rigs):
    rig = rigs([completion(tool_calls=[SLOW]), completion("xong")])
    with pytest.raises(EmptySteer):
        rig.inbound.stream(rig.conv.id, "/steer")
    assert not rig.hub.busy.busy(rig.conv.id) and rig.history() == []
    first = asyncio.create_task(collect(rig.inbound.stream(rig.conv.id, "việc 1")))
    await asyncio.wait_for(rig.slow.started.wait(), 2)
    with pytest.raises(EmptySteer):
        rig.inbound.stream(rig.conv.id, "/steer   ")
    assert rig.store.queue.count(rig.conv.id) == 0
    rig.slow.release.set()
    await asyncio.wait_for(first, 2)
    await settle_loop()
    assert rig.statuses() == ["done"]


async def test_a_message_past_the_limit_is_turned_away_and_the_line_kept(rigs):
    rig = rigs([completion(tool_calls=[SLOW]), completion("xong"), completion("đã đọc")])
    first = asyncio.create_task(collect(rig.inbound.stream(rig.conv.id, "việc 1")))
    await asyncio.wait_for(rig.slow.started.wait(), 2)
    for n in range(QUEUE_LIMIT):
        await collect(rig.inbound.stream(rig.conv.id, f"tin {n}"))
    for text in ("tin thừa", "/steer rẽ"):  # a steer waits in the same line
        with pytest.raises(QueueFull):
            rig.inbound.stream(rig.conv.id, text)
    rig.slow.release.set()
    await asyncio.wait_for(first, 2)
    await until(lambda: rig.statuses() == ["done", "done"])
    delivered = rig.history()[-2]
    assert delivered == ("user", "\n\n".join(f"tin {n}" for n in range(QUEUE_LIMIT)))


async def test_a_message_sent_before_the_turn_is_read_waits_whichever_door_it_used(rigs):
    rig = rigs([completion("một"), completion("hai")])
    other_door = Inbound({rig.deps.agent.id: rig.deps}, rig.hub)  # the bot's, say
    first = rig.inbound.stream(rig.conv.id, "tin 1")  # handed out, not read yet
    [queued] = await collect(other_door.stream(rig.conv.id, "tin 2"))
    assert queued.kind == FOLLOW_UP
    await collect(first)
    await until(lambda: rig.statuses() == ["done", "done"])
    assert rig.history() == [
        ("user", "tin 1"),
        ("assistant", "một"),
        ("user", "tin 2"),
        ("assistant", "hai"),
    ]


async def test_a_message_sent_while_a_call_awaits_a_decision_is_refused(rigs):
    rig = rigs([completion(tool_calls=[GUARDED])])
    await paused(rig)
    for text in ("tin 2", "/steer đổi hướng"):
        with pytest.raises(InboundBusy):
            rig.inbound.stream(rig.conv.id, text)
    assert rig.store.queue.count(rig.conv.id) == 0
    assert rig.statuses() == ["awaiting_approval"]


async def test_a_message_sent_right_after_a_decision_waits_for_the_turn_it_resumes(rigs):
    rig = rigs(
        [completion(tool_calls=[GUARDED]), completion("đã chạy"), completion("trả lời tin 2")]
    )
    pause = await paused(rig)
    resumed = rig.inbound.decide(rig.conv.id, pause.approval_id, True)  # not read yet
    assert rig.hub.busy.busy(rig.conv.id)
    [queued] = await collect(rig.inbound.stream(rig.conv.id, "tin 2"))
    assert queued.kind == FOLLOW_UP
    await collect(resumed)
    # The paused run carried on as the same run; the message got one of its own.
    await until(lambda: rig.statuses() == ["done", "done"])
    assert rig.guarded.runs == 1
    assert rig.history()[1:] == [
        ("assistant", ""),
        ("tool", "xong"),
        ("assistant", "đã chạy"),
        ("user", "tin 2"),
        ("assistant", "trả lời tin 2"),
    ]


async def test_a_message_that_waited_through_a_pause_is_answered_after_the_decision(rigs):
    rig = rigs(
        [
            completion(tool_calls=[SLOW]),
            completion(tool_calls=[GUARDED]),
            completion("đã chạy"),
            completion("trả lời tin 2"),
        ]
    )
    _, events = await while_the_tool_runs(rig, "tin 2")
    pause = events[-1]
    assert isinstance(pause, ApprovalRequiredEvent)
    await settle_loop()
    # A pause does not end the turn: the message keeps waiting for the decision's turn.
    assert rig.statuses() == ["awaiting_approval"] and rig.store.queue.count(rig.conv.id) == 1
    await collect(rig.inbound.decide(rig.conv.id, pause.approval_id, True))
    await until(lambda: rig.statuses() == ["done", "done"])
    assert rig.history()[-2:] == [("user", "tin 2"), ("assistant", "trả lời tin 2")]


async def test_a_second_decision_while_the_first_holds_the_conversation_is_turned_away(rigs):
    rig = rigs([completion(tool_calls=[ASK]), completion("chọn B")])
    question = await paused(rig, "hỏi tôi")
    first = rig.inbound.answer(rig.conv.id, question.approval_id, "B")
    with pytest.raises(InboundBusy):
        rig.inbound.answer(rig.conv.id, question.approval_id, "A")
    with pytest.raises(InboundBusy):
        rig.inbound.decide(rig.conv.id, question.approval_id, True)
    await collect(first)
    assert rig.history()[-2:] == [("tool", answer_result("B")), ("assistant", "chọn B")]
    assert rig.statuses() == ["done"]


async def test_the_expiry_sweep_leaves_a_request_a_decision_holds(rigs):
    rig = rigs([completion(tool_calls=[GUARDED]), completion("không chạy được")])
    pause = await paused(rig)
    agents, later = {rig.deps.agent.id: rig.deps}, datetime.now(UTC) + timedelta(hours=1)
    token = rig.hub.busy.claim(rig.conv.id)  # a decision taken, its turn not read yet
    assert await expire_overdue(agents, rig.hub, now=later) == []
    assert rig.store.approvals.get(pause.approval_id).status == PENDING
    rig.hub.busy.release(rig.conv.id, token)
    assert await expire_overdue(agents, rig.hub, now=later) == [pause.approval_id]
    assert rig.store.approvals.get(pause.approval_id).status == EXPIRED
    assert rig.guarded.runs == 0
    assert rig.history()[-2:] == [("tool", texts.EXPIRED_TOOL), ("assistant", "không chạy được")]
