"""Watching a turn while it runs (`activity/turn_watch.py`, `activity/tracked.py`): who
is there from the start reads every event, who arrives late starts from the answer being
written, who falls behind is resynced instead of cut off, and a turn's watchers are let go
the moment it is over or waits for a person, by that turn and no other."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.activity.tracked import tracked
from my_agent_crew.activity.turn_watch import WATCH_BACKLOG, Frame, Resync, TurnWatch
from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    Event,
    ModelCallEvent,
    TextDeltaEvent,
    ThinkingEvent,
    ToolCallDeltaEvent,
    ToolCallEvent,
)
from my_agent_crew.store.runs import AWAITING

CONV = "c1"
DONE = DoneEvent(spent_usd=0.0, unknown_cost_calls=0)


def text(piece: str) -> TextDeltaEvent:
    return TextDeltaEvent(text=piece)


def draft(chunk: str, index: int = 0, attempt: int = 0, name: str = "artifact_create"):
    return ToolCallDeltaEvent(index=index, name=name, chunk=chunk, attempt=attempt)


def stored(content: str = "xong") -> AssistantMessageEvent:
    return AssistantMessageEvent(
        message_id=1, content=content, tool_calls=[], provider="p", model="m", cost_usd=0.0
    )


async def read(frames: AsyncIterator[Frame], count: int) -> list[Frame]:
    async with asyncio.timeout(2):
        return [await anext(frames) for _ in range(count)]


async def rest(frames: AsyncIterator[Frame]) -> list[Frame]:
    async with asyncio.timeout(2):
        return [frame async for frame in frames]


def late(watch: TurnWatch) -> AsyncIterator[Frame]:
    frames = watch.join(CONV)
    assert frames is not None
    return frames


async def test_a_watcher_there_from_the_start_reads_every_event_then_stops():
    watch = TurnWatch()
    frames = watch.open(CONV).join(behind=False)
    turn = watch.begin(CONV)  # the turn that was opened, not another one
    events = [ModelCallEvent(stage="sent"), text("Xin "), text("chào"), stored("Xin chào"), DONE]
    for event in events:
        turn.publish(event)
    watch.end(CONV, turn)
    assert await rest(frames) == events
    assert watch.join(CONV) is None


async def test_a_conversation_with_no_turn_has_nothing_to_watch():
    watch = TurnWatch()
    assert watch.join(CONV) is None
    turn = watch.begin(CONV)
    assert watch.join("another") is None
    watch.end(CONV, turn)
    assert watch.join(CONV) is None


async def test_a_late_joiner_starts_from_the_answer_being_written():
    watch = TurnWatch()
    turn = watch.begin(CONV)
    for event in (ModelCallEvent(stage="sent"), text("Xin "), text("chào")):
        turn.publish(event)
    frames = late(watch)
    turn.publish(text(" bạn"))  # written before the joiner first reads: part of its start
    assert await read(frames, 1) == [Resync((text("Xin chào bạn"),))]
    turn.publish(text("!"))
    assert await read(frames, 1) == [text("!")]


async def test_a_resync_carries_the_thinking_and_the_canvas_being_drafted():
    watch = TurnWatch()
    turn = watch.begin(CONV)
    for event in (ModelCallEvent(stage="sent"), ThinkingEvent(), ModelCallEvent("first_token")):
        turn.publish(event)
    assert await read(late(watch), 1) == [Resync((ThinkingEvent(),))]
    turn.publish(text("Đây: "))  # the model went on to write: no longer thinking
    for event in (draft('{"title": "A", '), draft('"body": "một'), draft('{"t', index=1)):
        turn.publish(event)
    assert await read(late(watch), 1) == [
        Resync((text("Đây: "), draft('{"title": "A", "body": "một'), draft('{"t', index=1)))
    ]


async def test_an_attempt_called_off_takes_its_draft_with_it():
    watch = TurnWatch()
    turn = watch.begin(CONV)
    turn.publish(draft('{"title": "A"'))
    turn.publish(draft("", attempt=1, name=""))  # the chain gave that attempt up
    assert await read(late(watch), 1) == [Resync(())]
    turn.publish(draft('{"title": "A"'))
    turn.publish(draft('{"title": "B"', attempt=2))  # a new attempt starts the draft over
    assert await read(late(watch), 1) == [Resync((draft('{"title": "B"', attempt=2),))]


async def test_a_resync_in_place_of_the_last_events_says_the_turn_is_over():
    watch = TurnWatch()
    turn = watch.begin(CONV)
    turn.publish(text("dở dang"))
    frames = late(watch)
    turn.publish(ErrorEvent(message="hỏng"))  # the turn gave its answer up
    watch.end(CONV, turn)
    # Nothing is being written any more, and nothing follows.
    assert await rest(frames) == [Resync((), under_way=False)]


async def test_a_stored_answer_is_no_longer_being_written():
    watch = TurnWatch()
    turn = watch.begin(CONV)
    for event in (ThinkingEvent(), text("một"), draft('{"a"'), stored("một")):
        turn.publish(event)
    frames = late(watch)
    assert await read(frames, 1) == [Resync(())]  # it is in the conversation now
    call = ToolCallEvent(tool_call_id="c1", name="slow", arguments={})
    turn.publish(call)
    turn.publish(text("hai"))
    assert await read(frames, 2) == [call, text("hai")]
    assert await read(late(watch), 1) == [Resync((text("hai"),))]


async def test_a_watcher_too_far_behind_is_resynced_instead_of_cut_off():
    watch = TurnWatch()
    frames = watch.open(CONV).join(behind=False)
    turn = watch.begin(CONV)
    written = WATCH_BACKLOG + 5
    for _ in range(written):
        turn.publish(text("x"))
    # Not one of the events it could not keep up with, and all of them in the resync.
    assert await read(frames, 1) == [Resync((text("x" * written),))]
    turn.publish(text("y"))
    turn.publish(DONE)
    watch.end(CONV, turn)
    assert await rest(frames) == [text("y"), DONE]


async def test_a_watcher_within_the_backlog_loses_nothing():
    watch = TurnWatch()
    frames = watch.open(CONV).join(behind=False)
    turn = watch.begin(CONV)
    events = [text(str(n)) for n in range(WATCH_BACKLOG)]
    for event in events:
        turn.publish(event)
    watch.end(CONV, turn)
    assert await rest(frames) == events


async def test_a_watcher_that_leaves_is_held_nothing_for():
    watch = TurnWatch()
    turn = watch.begin(CONV)
    staying, leaving = late(watch), late(watch)
    assert await read(staying, 1) == await read(leaving, 1) == [Resync(())]
    await leaving.aclose()  # type: ignore[attr-defined]
    assert len(turn._watchers) == 1
    turn.publish(DONE)
    watch.end(CONV, turn)
    assert await rest(staying) == [DONE]


async def test_only_the_turn_under_way_is_ended_by_the_one_that_ran_it():
    watch = TurnWatch()
    first = watch.begin(CONV)
    old = late(watch)
    second = watch.begin(CONV)  # a turn that starts lets the earlier one's watchers go
    assert second is not first
    assert await rest(old) == [Resync((), under_way=False)]
    frames = late(watch)
    assert await read(frames, 1) == [Resync(())]
    watch.end(CONV, first)  # the earlier turn's reader finishing late
    assert watch.join(CONV) is not None  # the turn under way is still there to watch
    second.publish(DONE)
    assert await read(frames, 1) == [DONE]
    watch.end(CONV, second)
    assert await rest(frames) == []
    assert watch.join(CONV) is None


# --- a tracked turn ------------------------------------------------------------------------


@pytest.fixture
def hub(store) -> ActivityHub:
    return ActivityHub(store)


def run_of(hub: ActivityHub, events: AsyncIterator[Event], conv_id: str) -> AsyncIterator[Event]:
    return tracked(hub, events, "agent", "chat", "Việc thử", conv_id)


async def test_a_turn_lets_its_watchers_go_once_it_is_over_however_long_its_reader_takes(
    hub, store
):
    conv = store.create("Thử")
    lingering = asyncio.Event()

    async def turn() -> AsyncIterator[Event]:
        yield text("một")
        yield DONE
        await lingering.wait()  # the reader has not let go of the turn yet

    events = run_of(hub, turn(), conv.id)
    assert hub.turns.join(conv.id) is None  # nothing runs until the turn is first read
    assert await anext(events) == text("một")
    frames = hub.turns.join(conv.id)
    assert frames is not None
    assert await read(frames, 1) == [Resync((text("một"),))]
    assert await anext(events) == DONE
    assert await rest(frames) == [DONE]
    assert hub.turns.join(conv.id) is None
    lingering.set()
    assert [event async for event in events] == []


async def test_a_turn_waiting_for_a_person_is_not_under_way(hub, store):
    conv = store.create("Thử")
    pause = ApprovalRequiredEvent(approval_id="a1", tool_call_id="c1", name="guarded", arguments={})

    async def turn() -> AsyncIterator[Event]:
        yield pause

    events = run_of(hub, turn(), conv.id)
    frames = hub.turns.open(conv.id).join(behind=False)
    assert [event async for event in events] == [pause]
    assert await rest(frames) == [pause]
    assert hub.turns.join(conv.id) is None
    [run] = hub.recent(conversation_ids=[conv.id])
    assert run.status == AWAITING


async def test_a_turn_that_breaks_tells_its_watchers_so(hub, store):
    conv = store.create("Thử")

    async def turn() -> AsyncIterator[Event]:
        yield text("một")
        raise RuntimeError("hỏng")

    events = run_of(hub, turn(), conv.id)
    frames = hub.turns.open(conv.id).join(behind=False)
    assert await anext(events) == text("một")
    with pytest.raises(RuntimeError, match="hỏng"):
        await anext(events)
    assert await rest(frames) == [text("một"), ErrorEvent(message=texts.TURN_BROKE)]
    assert hub.turns.join(conv.id) is None
    [run] = hub.recent(conversation_ids=[conv.id])
    assert (run.status, run.summary) == ("error", "interrupted")


async def test_a_turn_whose_reader_stops_reading_lets_its_watchers_go(hub, store):
    conv = store.create("Thử")

    async def turn() -> AsyncIterator[Event]:
        yield text("một")
        await asyncio.Event().wait()

    events = run_of(hub, turn(), conv.id)
    frames = hub.turns.open(conv.id).join(behind=False)
    assert await anext(events) == text("một")
    await events.aclose()  # type: ignore[attr-defined]
    assert await rest(frames) == [text("một")]
    assert hub.turns.join(conv.id) is None
    [run] = hub.recent(conversation_ids=[conv.id])
    assert (run.status, run.summary) == ("error", "interrupted")
