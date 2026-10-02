"""A web message carries the canvas open in the tab that sent it. One conversation can be open
on two devices, each showing a different canvas, so the canvas the next note names is set as
the message is sent: checked before the gate, applied once the gate let the message through,
and left alone by a message the gate refuses or that carries no canvas at all."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.artifacts.diff import line_span
from my_agent_crew.config import Route
from my_agent_crew.server import create_app
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store.db import Store
from my_agent_crew.store.models import AWAITING_APPROVAL
from my_agent_crew.texts_canvas import CANVAS_NOTE_FOCUS, CANVAS_NOTE_PICK, PICK_LINES
from tests.canvas_helpers import framed, seen_canvas
from tests.test_server_api import parse_sse

PICK = {"version": 1, "text": "chạy 5 km", "line_start": 2, "line_end": 2}
ABSENT = object()


@pytest.fixture
def client(deps_factory):
    runtime = Runtime.single(deps_factory(routes=(Route("fake", "echo"),)))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        yield client


def _two_canvases(client: TestClient, store: Store) -> tuple[str, str, str]:
    """A conversation and two canvases its agent has seen, with the second open on the
    "phone"; the "laptop" still shows the first."""
    conv_id = client.post("/api/conversations", json={"title": "Thử"}).json()["id"]
    conv = store.get(conv_id)
    laptop, phone = seen_canvas(store, conv, "Bản X"), seen_canvas(store, conv, "Bản Y")
    put = client.put(f"/api/conversations/{conv_id}/canvas", json={"artifact_id": phone})
    assert put.status_code == 200, put.text
    return conv_id, laptop, phone


def _post(client: TestClient, conv_id: str, text: str, canvas=ABSENT):
    body = {"text": text} if canvas is ABSENT else {"text": text, "canvas": canvas}
    return client.post(f"/api/conversations/{conv_id}/messages", json=body)


def _send(client: TestClient, conv_id: str, text: str, canvas=ABSENT) -> str:
    response = _post(client, conv_id, text, canvas)
    assert response.status_code == 200, response.text
    return parse_sse(response.text)[-1]["type"]


def _opened(title: str, art: str) -> str:
    return framed(CANVAS_NOTE_FOCUS.format(title=title, id=art, version=1))


def test_a_message_names_the_canvas_open_in_the_tab_that_sent_it(client, store: Store):
    conv_id, laptop, _ = _two_canvases(client, store)
    assert _send(client, conv_id, "sửa đoạn kết", {"artifact_id": laptop}) == "done"
    sent = store.history(conv_id)[0]
    assert (sent.message.content, sent.context) == ("sửa đoạn kết", _opened("Bản X", laptop))
    assert store.artifact_links.focus(conv_id).artifact_id == laptop
    assert store.artifact_links.get(conv_id, laptop).shared is True


def test_a_message_quotes_the_passage_selected_in_its_canvas(client, store: Store):
    conv_id, laptop, _ = _two_canvases(client, store)
    _send(client, conv_id, "sửa chỗ này", {"artifact_id": laptop, "selection": PICK})
    where = PICK_LINES.format(span=line_span(2, 2), version=1)
    pick = CANVAS_NOTE_PICK.format(title="Bản X", id=laptop, where=where)
    assert store.history(conv_id)[0].context == framed(pick, "> chạy 5 km")
    assert store.artifact_links.focus(conv_id).selection is None


def test_a_message_without_a_canvas_leaves_the_open_one(client, store: Store):
    conv_id, _, phone = _two_canvases(client, store)
    _send(client, conv_id, "tiếp nhé")
    assert store.history(conv_id)[0].context == _opened("Bản Y", phone)
    assert store.artifact_links.focus(conv_id).artifact_id == phone


def test_a_message_from_a_tab_with_no_canvas_open_closes_it(client, store: Store):
    conv_id, _, _ = _two_canvases(client, store)
    _send(client, conv_id, "tiếp nhé", {"artifact_id": None})
    assert store.artifact_links.focus(conv_id) is None
    assert store.history(conv_id)[0].context == ""


def test_a_message_with_a_selection_the_note_would_drop_is_422_and_goes_nowhere(
    client, store: Store
):
    conv_id, laptop, _ = _two_canvases(client, store)
    before = store.artifact_links.focus(conv_id)
    bad = {"artifact_id": laptop, "selection": {**PICK, "version": 2}}
    assert _post(client, conv_id, "sửa", bad).status_code == 422
    client.app.state.runtime.hub.busy.claim(conv_id)
    assert _post(client, conv_id, "sửa", bad).status_code == 422
    assert (store.history(conv_id), store.queue.peek_all(conv_id)) == ([], [])
    assert store.artifact_links.focus(conv_id) == before
    assert store.artifact_links.get(conv_id, laptop).shared is False


def test_a_message_the_gate_refuses_leaves_the_open_canvas(client, store: Store):
    conv_id, laptop, _ = _two_canvases(client, store)
    store.update(conv_id, status=AWAITING_APPROVAL)
    before = store.artifact_links.focus(conv_id)
    refused = _post(client, conv_id, "sửa", {"artifact_id": laptop})
    assert (refused.status_code, refused.json()["detail"]) == (409, "awaiting approval")
    assert store.artifact_links.focus(conv_id) == before
    assert store.artifact_links.get(conv_id, laptop).shared is False
    missing = _post(client, "nope", "sửa", {"artifact_id": laptop})
    assert (missing.status_code, missing.json()["detail"]) == (404, "conversation not found")
    assert store.artifact_links.conversations_for(laptop) == [conv_id]


def test_a_message_from_a_tab_showing_a_deleted_canvas_still_goes_and_closes_it(
    client, store: Store
):
    conv_id, laptop, _ = _two_canvases(client, store)
    store.artifacts.delete(laptop)
    assert _send(client, conv_id, "sửa", {"artifact_id": laptop, "selection": PICK}) == "done"
    assert store.artifact_links.focus(conv_id) is None
    sent = store.history(conv_id)[0]
    assert (sent.message.content, sent.context) == ("sửa", "")


def test_a_queued_message_names_its_canvas_when_it_is_delivered(client, store: Store):
    conv_id, laptop, _ = _two_canvases(client, store)
    client.app.state.runtime.hub.busy.claim(conv_id)
    response = _post(client, conv_id, "sửa đoạn kết", {"artifact_id": laptop})
    [queued] = parse_sse(response.text)
    assert queued["type"] == "queued"
    assert store.artifact_links.focus(conv_id).artifact_id == laptop
    assert [item.text for item in store.queue.deliver(conv_id, [queued["item_id"]])] == [
        "sửa đoạn kết"
    ]
    assert store.history(conv_id)[-1].context == _opened("Bản X", laptop)


def test_the_open_canvas_is_named_once_while_messages_keep_carrying_it(client, store: Store):
    conv_id, laptop, _ = _two_canvases(client, store)
    for text in ("một", "hai"):
        _send(client, conv_id, text, {"artifact_id": laptop})
    first, _, second, _ = store.history(conv_id)
    assert (first.context, second.context) == (_opened("Bản X", laptop), "")
