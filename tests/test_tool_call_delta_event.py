"""The pieces of a canvas write go to the request that is streaming the turn and nowhere else.
Like a token, such an event is neither written with the run nor sent to the activity feed; it
changes nothing in the run's timeline, and it is no part of the one reply a chat platform or a
job reads. On the chat stream it is a frame of its own, with the four fields the web reads."""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import FrozenInstanceError

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.activity import ActivityHub
from my_agent_crew.activity.steps import apply_event
from my_agent_crew.agent.events import (
    STREAMING_EVENTS,
    AssistantMessageEvent,
    DoneEvent,
    Event,
    ModelCallEvent,
    ToolCallDeltaEvent,
    kind_of,
    to_dict,
)
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.agents.profile import DEFAULT_AGENT_ID
from my_agent_crew.config import DEFAULT_TOOL_OUTPUT_CHARS, Route
from my_agent_crew.server import create_app
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store.db import Store
from my_agent_crew.store.runs import RUNNING, RunRecord
from my_agent_crew.tools.artifact import build_artifact_tools
from my_agent_crew.turn_reply import collect_reply
from tests.canvas_helpers import ZONE
from tests.conftest import collect

ARGUMENTS = {"title": "Kế hoạch", "kind": "markdown", "content": "# Kế hoạch\nchạy 5 km\n"}
WRITTEN = json.dumps(ARGUMENTS, ensure_ascii=False)
WRITE = f"/tool artifact_create {WRITTEN}"
PIECE = ToolCallDeltaEvent(index=0, name="artifact_create", chunk=WRITTEN[:12], attempt=0)


@pytest.fixture
def deps(deps_factory, store: Store) -> AgentDeps:
    """The offline model with the canvas tools, so a message can make it write a canvas."""
    tools = build_artifact_tools(store, DEFAULT_AGENT_ID, False, DEFAULT_TOOL_OUTPUT_CHARS, ZONE)
    return deps_factory(routes=(Route("fake", "echo"),), extra_tools=tools)


@pytest.fixture
def client(deps: AgentDeps):
    with TestClient(
        create_app(Runtime.single(deps), schedule=False), base_url="http://127.0.0.1"
    ) as client:
        yield client


def _named(sse: str) -> list[tuple[str, dict]]:
    """A turn's stream as (event name, payload) pairs, in the order it arrived."""
    pairs = []
    for block in sse.replace("\r\n", "\n").strip().split("\n\n"):
        lines = block.splitlines()
        name = next(line[6:].strip() for line in lines if line.startswith("event:"))
        data = "".join(line[5:].strip() for line in lines if line.startswith("data:"))
        pairs.append((name, json.loads(data)))
    return pairs


def _pieces(events: Sequence[Event]) -> list[ToolCallDeltaEvent]:
    return [event for event in events if isinstance(event, ToolCallDeltaEvent)]


async def _replayed(events: Sequence[Event]) -> AsyncIterator[Event]:
    for event in events:
        yield event


def test_its_payload_is_the_piece_its_call_and_the_attempt_that_wrote_it():
    event = ToolCallDeltaEvent(index=1, name="artifact_rewrite", chunk='{"id"', attempt=2)
    assert kind_of(event) == "tool_call_delta"
    assert to_dict(event) == {
        "type": "tool_call_delta",
        "index": 1,
        "name": "artifact_rewrite",
        "chunk": '{"id"',
        "attempt": 2,
    }


def test_it_cannot_be_changed_once_it_is_made():
    """The same object passes the stream and the activity hub's filter: a piece one of them
    could rewrite is a piece the tab would draw and the model never wrote."""
    with pytest.raises(FrozenInstanceError):
        PIECE.chunk = "đã đổi"  # type: ignore[misc]
    assert PIECE.chunk == WRITTEN[:12]


def test_it_is_one_of_the_events_that_only_stream():
    assert ToolCallDeltaEvent in STREAMING_EVENTS


async def test_a_turn_that_writes_a_canvas_shows_a_piece_before_the_answer(
    deps: AgentDeps, store: Store
):
    conv = store.create()
    events = await collect(run_turn(deps, conv.id, WRITE))
    assert _pieces(events)[0] == PIECE
    answer = next(event for event in events if isinstance(event, AssistantMessageEvent))
    assert events.index(PIECE) < events.index(answer)
    assert answer.tool_calls[0]["arguments"] == ARGUMENTS
    assert isinstance(events[-1], DoneEvent)
    assert [canvas.title for canvas in store.artifacts.list()] == ["Kế hoạch"]


async def test_the_activity_hub_neither_writes_nor_broadcasts_it(store: Store, monkeypatch):
    hub = ActivityHub(store)
    stream = hub.subscribe()
    assert (await anext(stream))["type"] == "snapshot"
    run = hub.start("default", "chat", "t", None)
    assert (await anext(stream))["type"] == "run"
    saves: list[str] = []
    real_save = store.runs.save
    monkeypatch.setattr(store.runs, "save", lambda run: saves.append(run.status) or real_save(run))

    hub.record(run, PIECE, 1.0)
    hub.record(run, ToolCallDeltaEvent(index=0, name="", chunk="", attempt=1), 1.0)
    assert saves == []
    hub.record(run, DoneEvent(0.0, 0), 1.1)
    assert saves != []
    heard = await asyncio.wait_for(anext(stream), 2)
    assert (heard["type"], heard["event"]["type"]) == ("event", "done")  # nothing came before it


@pytest.mark.parametrize("opened", [False, True], ids=["no step yet", "a model step under way"])
def test_it_leaves_a_run_exactly_as_it_was(opened: bool):
    """It opens no step and moves no counter: the model step is timed from the request and
    from the first chunk, and a document's size is not the length of an answer."""
    run = RunRecord("r1", "default", "c1", "chat", "t", RUNNING, "2026-10-05T08:00:00")
    if opened:
        apply_event(run, ModelCallEvent("sent"), 10.0)
        apply_event(run, ModelCallEvent("first_token"), 10.4)
    before = copy.deepcopy(run)

    apply_event(run, PIECE, 11.0)
    apply_event(run, ToolCallDeltaEvent(index=0, name="", chunk="", attempt=1), 12.0)

    assert run == before
    assert len(run.steps) == (1 if opened else 0)


async def test_a_reply_reads_the_same_with_the_pieces_in_the_chain_or_without_them(
    deps: AgentDeps, store: Store
):
    conv = store.create()
    events = await collect(run_turn(deps, conv.id, WRITE))
    without = [event for event in events if not isinstance(event, ToolCallDeltaEvent)]
    assert len(without) < len(events)
    reply = await collect_reply(_replayed(events))
    assert reply == await collect_reply(_replayed(without))
    assert (reply.status, reply.steps) == ("done", 2)


def test_the_tab_that_sent_the_message_reads_the_piece_as_a_frame_of_its_own(
    client: TestClient,
):
    conv_id = client.post("/api/conversations", json={"title": "Thử"}).json()["id"]
    response = client.post(f"/api/conversations/{conv_id}/messages", json={"text": WRITE})
    assert response.status_code == 200, response.text
    stream = _named(response.text)

    names = [name for name, _ in stream]
    payload = next(payload for name, payload in stream if name == "tool_call_delta")
    assert payload == {
        "type": "tool_call_delta",
        "index": 0,
        "name": "artifact_create",
        "chunk": WRITTEN[:12],
        "attempt": 0,
    }
    assert names.index("tool_call_delta") < names.index("assistant_message")
    assert names[-1] == "done"


def test_a_turn_that_calls_another_tool_streams_no_such_frame(client: TestClient):
    conv_id = client.post("/api/conversations", json={"title": "Thử"}).json()["id"]
    text = '/tool workspace_list {"path": "."}'
    response = client.post(f"/api/conversations/{conv_id}/messages", json={"text": text})
    names = [name for name, _ in _named(response.text)]
    assert "tool_call" in names and names[-1] == "done"
    assert "tool_call_delta" not in names
