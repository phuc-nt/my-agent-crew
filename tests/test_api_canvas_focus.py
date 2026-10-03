"""The canvas a conversation has open on the web, with the passage the person selected in it.
Opening a canvas shares it with the conversation, so the agents it delegates to reach it too,
and a selection is checked the way the next turn's note will read it: one the note would drop
is refused, never stored."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.server import create_app
from my_agent_crew.store.db import Store
from tests.canvas_helpers import PLAN, agents_canvas, persons_canvas

PICK = {"version": 1, "text": "chạy 5 km", "line_start": 2, "line_end": 2}


@pytest.fixture
def client(deps_factory):
    app = create_app(deps_factory(), schedule=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client


def _open(client: TestClient, conv_id: str, artifact_id: str | None, selection=None):
    body = {"artifact_id": artifact_id, "selection": selection}
    return client.put(f"/api/conversations/{conv_id}/canvas", json=body)


def test_the_open_canvas_and_its_selection_read_back(client, store: Store):
    conv, art = store.create(), persons_canvas(store, PLAN)
    assert client.get(f"/api/conversations/{conv.id}/canvas").json() is None
    response = _open(client, conv.id, art, PICK)
    assert (response.status_code, response.json()) == (200, {"artifact_id": art, "selection": PICK})
    assert client.get(f"/api/conversations/{conv.id}/canvas").json() == response.json()
    assert _open(client, conv.id, art).json() == {"artifact_id": art, "selection": None}
    assert store.artifact_links.focus(conv.id).selection is None


def test_closing_the_canvas_clears_what_is_open(client, store: Store):
    conv, art = store.create(), persons_canvas(store, PLAN)
    _open(client, conv.id, art, PICK)
    response = _open(client, conv.id, None)
    assert (response.status_code, response.json()) == (200, None)
    assert store.artifact_links.focus(conv.id) is None
    assert client.get(f"/api/conversations/{conv.id}/canvas").json() is None


def test_a_selection_with_no_canvas_open_is_422(client, store: Store):
    conv, art = store.create(), persons_canvas(store, PLAN)
    _open(client, conv.id, art)
    assert _open(client, conv.id, None, PICK).status_code == 422
    assert store.artifact_links.focus(conv.id).artifact_id == art


def test_opening_a_canvas_the_agent_only_read_shares_it(client, store: Store):
    conv, art = store.create(), agents_canvas(store, "coach", PLAN)
    store.artifact_links.mark_seen(conv.id, art, 1)
    assert store.artifact_links.get(conv.id, art).shared is False
    _open(client, conv.id, art)
    link = store.artifact_links.get(conv.id, art)
    assert (link.shared, link.seen_version) == (True, 1)


def test_opening_an_unlinked_canvas_links_it_shared_and_unseen(client, store: Store):
    conv, art = store.create(), persons_canvas(store, PLAN)
    _open(client, conv.id, art)
    link = store.artifact_links.get(conv.id, art)
    assert (link.shared, link.seen_version) == (True, 0)


def test_a_canvas_opened_on_the_web_reaches_the_agents_the_conversation_delegates_to(
    client, store: Store
):
    parent = store.create()
    child = store.create(root_id=parent.id)
    opened, read = persons_canvas(store, PLAN), agents_canvas(store, "pong", PLAN)
    store.artifact_links.mark_seen(parent.id, read, 1)
    _open(client, parent.id, opened)
    reach = store.artifacts.is_reachable
    assert reach(opened, child.id, root_id=parent.id, agent_id="coach") is True
    assert reach(read, child.id, root_id=parent.id, agent_id="coach") is False


@pytest.mark.parametrize(
    "change",
    [
        {"version": True},
        {"version": 0},
        {"version": 2},
        {"version": "1"},
        {"line_start": 2.0},
        {"line_end": False},
        {"text": "   \n"},
        {"text": "x" * 20001},
        {"line_start": 3, "line_end": 2},
    ],
    ids=[
        "version-bool",
        "version-zero",
        "version-past-head",
        "version-string",
        "line-float",
        "line-bool",
        "blank-text",
        "long-text",
        "lines-backwards",
    ],
)
def test_a_selection_the_note_would_drop_is_422_and_nothing_changes(client, store: Store, change):
    conv, art = store.create(), persons_canvas(store, PLAN)
    _open(client, conv.id, art, PICK)
    before = store.artifact_links.focus(conv.id)
    response = _open(client, conv.id, art, {**PICK, **change})
    assert response.status_code == 422
    assert store.artifact_links.focus(conv.id) == before


def _open_on_the_wire(client: TestClient, conv_id: str, artifact_id: str, selection: dict):
    """`_open` for a body httpx would refuse to encode: a lone surrogate goes as the escape
    a browser's `JSON.stringify` makes of it."""
    return client.put(
        f"/api/conversations/{conv_id}/canvas",
        content=json.dumps({"artifact_id": artifact_id, "selection": selection}),
        headers={"content-type": "application/json"},
    )


def test_a_selection_cut_through_a_character_is_422_and_nothing_changes(client, store: Store):
    conv, art = store.create(), persons_canvas(store, PLAN)
    _open(client, conv.id, art, PICK)
    before = store.artifact_links.focus(conv.id)
    # Half an emoji, as a cut between the two code units of a character leaves it.
    half = {**PICK, "text": "chạy 5 km \ud83d"}
    assert _open_on_the_wire(client, conv.id, art, half).status_code == 422
    assert store.artifact_links.focus(conv.id) == before


def test_a_selection_with_a_whole_emoji_in_it_is_stored(client, store: Store):
    conv, art = store.create(), persons_canvas(store, PLAN)
    whole = {**PICK, "text": "chạy 5 km \U0001f3c3"}
    assert _open_on_the_wire(client, conv.id, art, whole).status_code == 200
    assert store.artifact_links.focus(conv.id).selection == whole


def test_a_selection_may_reach_twenty_thousand_characters(client, store: Store):
    conv, art = store.create(), persons_canvas(store, PLAN)
    selection = {**PICK, "text": "x" * 20000}
    assert _open(client, conv.id, art, selection).status_code == 200
    assert store.artifact_links.focus(conv.id).selection == selection


def test_a_missing_conversation_or_canvas_is_404(client, store: Store):
    conv, art = store.create(), persons_canvas(store, PLAN)
    missing = client.get("/api/conversations/nope/canvas")
    assert (missing.status_code, missing.json()["detail"]) == (404, "conversation not found")
    response = _open(client, "nope", art)
    assert (response.status_code, response.json()["detail"]) == (404, "conversation not found")
    response = _open(client, conv.id, "nope")
    assert (response.status_code, response.json()["detail"]) == (404, "artifact not found")
    assert store.artifact_links.focus(conv.id) is None
    assert store.artifact_links.get(conv.id, art) is None
