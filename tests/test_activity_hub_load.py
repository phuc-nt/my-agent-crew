"""What the hub does under load: tokens stay in memory, and a stalled watcher is cut off."""

import asyncio

from my_agent_crew.activity import ActivityHub
from my_agent_crew.activity.hub import SUBSCRIBER_QUEUE_SIZE
from my_agent_crew.agent.events import (
    AssistantMessageEvent,
    DoneEvent,
    TextDeltaEvent,
    ThinkingEvent,
    kind_of,
)
from my_agent_crew.store import Store
from my_agent_crew.store.runs import DONE
from tests.conftest import collect


async def test_streamed_tokens_are_neither_written_nor_broadcast(store: Store, monkeypatch):
    hub = ActivityHub(store)
    saves: list[str] = []
    real_save = store.runs.save
    monkeypatch.setattr(store.runs, "save", lambda run: saves.append(run.status) or real_save(run))
    seen: list[dict] = []

    async def watch():
        async for payload in hub.subscribe():
            seen.append(payload)
            if payload["type"] == "run" and payload["run"]["status"] == DONE:
                return

    watcher = asyncio.create_task(watch())
    await asyncio.sleep(0)
    run = hub.start("default", "chat", "t", None)
    hub.record(run, ThinkingEvent(), 1.0)
    for word in ("xin ", "chào ", "bạn"):
        hub.record(run, TextDeltaEvent(word), 1.1)
    saves_before_message = len(saves)
    message = AssistantMessageEvent(1, "xin chào bạn", [], "p", "m", 0.001)
    hub.record(run, message, 1.5)
    hub.record(run, DoneEvent(0.001, 0), 1.5)
    await asyncio.wait_for(watcher, 2)

    assert saves_before_message == 1  # only `start` wrote; four streamed events did not
    assert run.steps[0]["chars"] == len("xin chào bạn")  # yet the step saw every token
    event_types = [p["event"]["type"] for p in seen if p["type"] == "event"]
    assert event_types == [kind_of(message), kind_of(DoneEvent(0.001, 0))]


async def test_a_watcher_that_stops_reading_is_dropped_and_its_stream_ends(store: Store):
    hub = ActivityHub(store)
    stream = hub.subscribe()
    assert (await anext(stream))["type"] == "snapshot"
    for index in range(SUBSCRIBER_QUEUE_SIZE + 1):
        hub.publish_conversation({"id": f"c{index}"})
    delivered = await asyncio.wait_for(collect(stream), 2)
    assert 0 < len(delivered) <= SUBSCRIBER_QUEUE_SIZE
    hub.publish_conversation({"id": "after"})  # nobody left to overflow

    fresh: list[dict] = []

    async def watch():
        async for payload in hub.subscribe():
            fresh.append(payload)
            if payload["type"] == "conversation":
                return

    watcher = asyncio.create_task(watch())
    await asyncio.sleep(0)
    hub.publish_conversation({"id": "new"})
    await asyncio.wait_for(watcher, 2)
    assert fresh[-1]["conversation"] == {"id": "new"}
