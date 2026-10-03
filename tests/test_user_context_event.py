"""A message stored with a canvas note streams that note back on its sender's own stream, so
the bubble the web drew before the server had stored anything can show it as a chip. It is a
streaming event like a token, and more private: neither the activity feed nor a chat platform
that reads a turn as one reply ever sees it, and only a turn that took a new message sends it."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import FrozenInstanceError

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.events import (
    AssistantMessageEvent,
    DoneEvent,
    Event,
    UserContextEvent,
    kind_of,
    to_dict,
)
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.config import Route
from my_agent_crew.server import create_app
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store
from my_agent_crew.turn_reply import collect_reply
from tests.canvas_helpers import SWIM, edited, framed, say, seen_canvas
from tests.conftest import collect

PICK = {"version": 1, "text": "chạy 5 km", "line_start": 2, "line_end": 2}


@pytest.fixture
def deps(deps_factory) -> AgentDeps:
    return deps_factory(routes=(Route("fake", "echo"),))


@pytest.fixture
def client(deps: AgentDeps):
    with TestClient(
        create_app(Runtime.single(deps), schedule=False), base_url="http://127.0.0.1"
    ) as client:
        yield client


def _after_an_edit(store: Store) -> tuple[str, str]:
    """A conversation whose canvas the person changed after the agent saw it, and the note
    their next message is stored with."""
    conv = store.create()
    art = seen_canvas(store, conv)
    store.artifacts.write(art, SWIM, USER, "")
    return conv.id, framed(*edited("Kế hoạch", art))


def _notes(events: Sequence[Event]) -> list[UserContextEvent]:
    return [event for event in events if isinstance(event, UserContextEvent)]


async def _replayed(events: Sequence[Event]) -> AsyncIterator[Event]:
    for event in events:
        yield event


def _named(sse: str) -> list[tuple[str, dict]]:
    """A turn's stream as (event name, payload) pairs, in the order it arrived."""
    pairs = []
    for block in sse.replace("\r\n", "\n").strip().split("\n\n"):
        lines = block.splitlines()
        name = next(line[6:].strip() for line in lines if line.startswith("event:"))
        data = "".join(line[5:].strip() for line in lines if line.startswith("data:"))
        pairs.append((name, json.loads(data)))
    return pairs


def test_its_payload_is_the_note_and_nothing_else():
    event = UserContextEvent("ghi chú")
    assert kind_of(event) == "user_context"
    assert to_dict(event) == {"type": "user_context", "context": "ghi chú"}


def test_it_cannot_be_changed_once_it_is_made():
    """The same object passes the stream, the activity hub's filter and the reply a chat platform
    collects: if one of them could rewrite the note, the next would read what no message carried."""
    event = UserContextEvent("ghi chú")
    with pytest.raises(FrozenInstanceError):
        event.context = "đã đổi"  # type: ignore[misc]
    assert event.context == "ghi chú"


async def test_the_first_event_of_a_turn_is_the_note_its_message_was_stored_with(
    deps: AgentDeps, store: Store
):
    conv_id, note = _after_an_edit(store)
    events = await collect(run_turn(deps, conv_id, "tiếp nhé"))
    assert events[0] == UserContextEvent(note)
    assert store.history(conv_id)[0].context == note
    assert len(_notes(events)) == 1


async def test_a_message_stored_without_a_note_streams_none(deps: AgentDeps, store: Store):
    conv = store.create()
    events = await collect(run_turn(deps, conv.id, "xin chào"))
    assert store.history(conv.id)[0].context == ""
    assert _notes(events) == []
    assert isinstance(events[-1], DoneEvent)


async def test_a_turn_that_takes_no_new_message_streams_no_note(deps: AgentDeps, store: Store):
    """The turn that goes on after an approval answers a message stored earlier, and the
    chip for it was sent with that turn's first stream, if the tab was there to read it."""
    conv_id, _ = _after_an_edit(store)
    assert say(store, store.get(conv_id))  # the message waiting to be answered carries a note
    events = await collect(run_turn(deps, conv_id, None))
    assert any(isinstance(event, AssistantMessageEvent) for event in events)
    assert _notes(events) == []


async def test_the_activity_hub_neither_writes_nor_broadcasts_it(store: Store, monkeypatch):
    hub = ActivityHub(store)
    stream = hub.subscribe()
    assert (await anext(stream))["type"] == "snapshot"
    run = hub.start("default", "chat", "t", None)
    assert (await anext(stream))["type"] == "run"
    saves: list[str] = []
    real_save = store.runs.save
    monkeypatch.setattr(store.runs, "save", lambda run: saves.append(run.status) or real_save(run))

    hub.record(run, UserContextEvent(framed("một dòng của người")), 1.0)
    assert saves == []
    hub.record(run, DoneEvent(0.0, 0), 1.1)
    heard = await asyncio.wait_for(anext(stream), 2)
    assert (heard["type"], heard["event"]["type"]) == ("event", "done")  # nothing came before it


async def test_a_reply_reads_the_same_with_the_note_in_the_chain_or_without_it(
    deps: AgentDeps, store: Store
):
    conv_id, _ = _after_an_edit(store)
    events = await collect(run_turn(deps, conv_id, "tiếp nhé"))
    without = [event for event in events if not isinstance(event, UserContextEvent)]
    assert len(without) == len(events) - 1
    reply = await collect_reply(_replayed(events))
    assert reply == await collect_reply(_replayed(without))
    assert (reply.status, reply.steps) == ("done", 1)
    assert "(echo)" in reply.text


def _send(client: TestClient, conv_id: str, **body) -> list[tuple[str, dict]]:
    response = client.post(f"/api/conversations/{conv_id}/messages", json=body)
    assert response.status_code == 200, response.text
    return _named(response.text)


def test_the_sender_reads_the_selected_passage_in_the_first_event_of_its_stream(
    client: TestClient, store: Store
):
    conv_id = client.post("/api/conversations", json={"title": "Thử"}).json()["id"]
    art = seen_canvas(store, store.get(conv_id))
    canvas = {"artifact_id": art, "selection": PICK}

    stream = _send(client, conv_id, text="sửa chỗ này", canvas=canvas)

    name, payload = stream[0]
    assert (name, payload["type"]) == ("user_context", "user_context")
    assert set(payload) == {"type", "context"}
    assert "> chạy 5 km" in payload["context"]
    assert payload["context"] == store.history(conv_id)[0].context
    assert stream[-1][0] == "done"


def test_a_message_that_was_stored_without_a_note_opens_with_no_such_event(
    client: TestClient,
):
    conv_id = client.post("/api/conversations", json={"title": "Thử"}).json()["id"]
    names = [name for name, _ in _send(client, conv_id, text="xin chào")]
    assert "user_context" not in names
    assert names[-1] == "done"


def test_a_message_the_server_queued_gets_no_such_event_either(client: TestClient, store: Store):
    """Its note is built when the turn that is running reads it, long after this stream
    ended with `queued`; the chip for it comes with the next load of the conversation."""
    conv_id, _ = _after_an_edit(store)
    client.app.state.runtime.hub.busy.claim(conv_id)
    assert [name for name, _ in _send(client, conv_id, text="việc nối tiếp")] == ["queued"]
