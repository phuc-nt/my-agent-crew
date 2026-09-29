"""Handing the running turn a message with `/steer text` or a kit command: taken between
steps, after the result of the tool already running and before the next model call, and
answered by that same turn rather than by one after it."""

from __future__ import annotations

import asyncio

from my_agent_crew.agent.events import (
    AssistantMessageEvent,
    DoneEvent,
    ModelCallEvent,
    QueuedEvent,
    SteerEvent,
    ToolResultEvent,
)
from my_agent_crew.agent.loop_guard import OK, REDIRECT, LoopGuard
from my_agent_crew.agent.steer import take_steers
from my_agent_crew.agents.kit_commands import Command
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store.queue import FOLLOW_UP, STEER
from tests.conftest import collect
from tests.queue_helpers import while_the_tool_runs

SLOW = ToolCall("c1", "slow", {})
FOCUS = Command("focus", "Tập trung.", "Tập trung vào $ARGUMENTS.")


def index_of(events: list, kind: type, nth: int = 0) -> int:
    return [i for i, event in enumerate(events) if isinstance(event, kind)][nth]


async def test_a_steer_reaches_the_running_turn_after_the_tool_it_waited_for(rigs):
    rig = rigs([completion(tool_calls=[SLOW]), completion("đã thêm X")])
    [[queued]], events = await while_the_tool_runs(rig, "/steer thêm X")
    assert queued == QueuedEvent(item_id=queued.item_id, kind=STEER, position=1)
    assert SteerEvent(text="thêm X", count=1) in events
    steer = events.index(SteerEvent(text="thêm X", count=1))
    assert index_of(events, ToolResultEvent) < steer < index_of(events, ModelCallEvent, 1)
    assert isinstance(events[-1], DoneEvent)
    sent = list(rig.provider.requests[1].messages)
    assert [(m.role, m.content) for m in sent[-2:]] == [("tool", "xong"), ("user", "thêm X")]
    assert rig.history()[-3:] == [("tool", "xong"), ("user", "thêm X"), ("assistant", "đã thêm X")]
    assert rig.statuses() == ["done"] and rig.store.queue.count(rig.conv.id) == 0
    [step] = [s for s in rig.runs()[0].steps if s["kind"] == "steer"]
    assert step == {"kind": "steer", "text": "thêm X", "duration_ms": 0}


async def test_steers_sent_in_one_step_arrive_together(rigs):
    rig = rigs([completion(tool_calls=[SLOW]), completion("ok")])
    answers, events = await while_the_tool_runs(rig, "/steer thêm X", "/steer\nbỏ Y")
    assert [answer[0].position for answer in answers] == [1, 2]
    assert [e for e in events if isinstance(e, SteerEvent)] == [
        SteerEvent(text="thêm X\n\nbỏ Y", count=2)
    ]
    assert rig.provider.requests[1].messages[-1].content == "thêm X\n\nbỏ Y"
    [step] = [s for s in rig.runs()[0].steps if s["kind"] == "steer"]
    assert step["text"] == "thêm X bỏ Y"  # one line on the timeline


async def test_a_steer_sent_while_the_answer_streams_is_answered_by_the_same_turn(rigs):
    rig = rigs([completion("trả lời đầu"), completion("trả lời phần rẽ")], held=(0,))
    first = asyncio.create_task(collect(rig.inbound.stream(rig.conv.id, "hỏi")))
    await asyncio.wait_for(rig.provider.started(0).wait(), 2)
    await collect(rig.inbound.stream(rig.conv.id, "/steer thêm Y"))
    rig.provider.release(0)
    events = await asyncio.wait_for(first, 2)
    answers = [e.content for e in events if isinstance(e, AssistantMessageEvent)]
    assert answers == ["trả lời đầu", "trả lời phần rẽ"]
    assert [e for e in events if isinstance(e, DoneEvent)] == [events[-1]]
    assert rig.history()[-3:] == [
        ("assistant", "trả lời đầu"),
        ("user", "thêm Y"),
        ("assistant", "trả lời phần rẽ"),
    ]
    assert rig.statuses() == ["done"]


async def test_a_kit_command_sent_while_busy_is_expanded_and_steered(rigs):
    rig = rigs([completion(tool_calls=[SLOW]), completion("ok")], commands=[FOCUS])
    [[queued]], events = await while_the_tool_runs(rig, "/focus chi phí")
    assert queued.kind == STEER
    assert SteerEvent(text="Tập trung vào chi phí.", count=1) in events
    assert rig.provider.requests[1].messages[-1].content == "Tập trung vào chi phí."


async def test_take_steers_leaves_follow_ups_and_starts_the_repeat_count_over(deps_factory):
    deps = deps_factory()
    conv = deps.store.create()
    calls = [{"name": "shell_run", "arguments": {"command": "ls"}}]
    quiet, steered = LoopGuard(), LoopGuard()
    for guard in (quiet, steered):
        assert [guard.observe(calls), guard.observe(calls)] == [OK, OK]
    deps.store.queue.add(conv.id, FOLLOW_UP, "sau", "chat")
    assert await collect(take_steers(deps, conv.id, quiet)) == []
    assert quiet.observe(calls) == REDIRECT  # no steer: the third repeat in a row
    deps.store.queue.add(conv.id, STEER, "đổi cách", "chat")
    assert await collect(take_steers(deps, conv.id, steered)) == [
        SteerEvent(text="đổi cách", count=1)
    ]
    # New words from the person: the count starts over.
    assert [steered.observe(calls) for _ in range(3)] == [OK, OK, REDIRECT]
    assert [i.text for i in deps.store.queue.peek_all(conv.id)] == ["sau"]
