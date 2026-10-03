"""A web message carries the canvas open in the tab that sent it. One conversation can be open
on two devices, each showing a different canvas, so the canvas the next note names is set as
the message is sent: checked before the gate, applied once the gate let the message through,
and left alone by a message the gate refuses or that carries no canvas at all."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.artifacts.diff import line_span
from my_agent_crew.config import Route
from my_agent_crew.server import create_app
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store.db import Store
from my_agent_crew.store.models import AWAITING_APPROVAL
from my_agent_crew.texts_canvas import (
    CANVAS_NOTE_FOCUS,
    CANVAS_NOTE_PICK,
    PICK_LINES,
    PICK_TEXT,
)
from tests.canvas_helpers import framed, persons_canvas, seen_canvas
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


def _post_wire(client: TestClient, conv_id: str, text: str, canvas):
    """`_post` for a body httpx would refuse to encode: the text goes as the wire has it, with
    a lone surrogate as the escape a browser's `JSON.stringify` makes of it."""
    content = json.dumps({"text": text, "canvas": canvas})
    return client.post(
        f"/api/conversations/{conv_id}/messages",
        content=content,
        headers={"content-type": "application/json"},
    )


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


def test_a_queued_ask_keeps_its_passage_until_it_is_delivered(client, store: Store):
    conv_id, laptop, _ = _two_canvases(client, store)
    client.app.state.runtime.hub.busy.claim(conv_id)
    [queued] = parse_sse(
        _post(client, conv_id, "sửa chỗ này", {"artifact_id": laptop, "selection": PICK}).text
    )
    assert store.artifact_links.focus(conv_id).selection is not None
    store.queue.deliver(conv_id, [queued["item_id"]])
    where = PICK_LINES.format(span=line_span(2, 2), version=1)
    pick = CANVAS_NOTE_PICK.format(title="Bản X", id=laptop, where=where)
    assert store.history(conv_id)[-1].context == framed(pick, "> chạy 5 km")


def test_a_queued_ask_loses_its_passage_to_a_later_message_from_the_same_tab(client, store: Store):
    # A known limit: a queued note is built when it is delivered, from the focus as it stands
    # then, and the later message's own `canvas` has already cleared the selection.
    conv_id, laptop, _ = _two_canvases(client, store)
    client.app.state.runtime.hub.busy.claim(conv_id)
    ask = {"artifact_id": laptop, "selection": PICK}
    [first] = parse_sse(_post(client, conv_id, "sửa chỗ này", ask).text)
    [second] = parse_sse(
        _post(client, conv_id, "và cả chỗ kia", {"artifact_id": laptop, "selection": None}).text
    )
    assert (first["type"], second["type"]) == ("queued", "queued")
    assert store.artifact_links.focus(conv_id).selection is None
    store.queue.deliver(conv_id, [first["item_id"]])
    context = store.history(conv_id)[-1].context
    assert context == _opened("Bản X", laptop)
    assert "chạy 5 km" not in context


def test_a_selection_cut_through_a_character_is_422_and_goes_nowhere(client, store: Store):
    conv_id, laptop, _ = _two_canvases(client, store)
    before = store.artifact_links.focus(conv_id)
    # Half an emoji, as a cut between the two code units of a character leaves it. No row can
    # hold it, so it must be refused before the message is queued, not when focus is written.
    cut = {"artifact_id": laptop, "selection": {**PICK, "text": "chạy 5 km \ud83d"}}
    assert _post_wire(client, conv_id, "sửa", cut).status_code == 422
    client.app.state.runtime.hub.busy.claim(conv_id)
    assert _post_wire(client, conv_id, "sửa", cut).status_code == 422
    assert (store.history(conv_id), store.queue.peek_all(conv_id)) == ([], [])
    assert store.artifact_links.focus(conv_id) == before
    assert store.artifact_links.get(conv_id, laptop).shared is False


def test_a_selection_with_a_whole_emoji_in_it_goes_with_the_message(client, store: Store):
    conv_id, laptop, _ = _two_canvases(client, store)
    emoji = {**PICK, "text": "chạy 5 km \U0001f3c3"}
    assert (
        _post_wire(client, conv_id, "sửa", {"artifact_id": laptop, "selection": emoji}).status_code
        == 200
    )
    assert store.history(conv_id)[0].message.content == "sửa"


def _long_canvas(store: Store, conv_id: str) -> tuple[str, list[str]]:
    lines = [f"dòng {n:03d} " + "ă" * 60 for n in range(1, 400)]
    return persons_canvas(store, "\n".join(lines), conv_id), lines


def _cut_at_a_line_end(lines: list[str], limit: int = 20000) -> dict:
    """The longest run of whole lines from the first that fits `limit` characters, as the
    web cuts a selection: at a line break, with the end line lowered to match."""
    count = max(n for n in range(1, len(lines) + 1) if len("\n".join(lines[:n])) <= limit)
    return {"version": 1, "text": "\n".join(lines[:count]), "line_start": 1, "line_end": count}


def test_a_selection_cut_at_a_line_end_is_still_placed_by_its_lines(client, store: Store):
    conv_id = client.post("/api/conversations", json={"title": "Dài"}).json()["id"]
    art, lines = _long_canvas(store, conv_id)
    cut = _cut_at_a_line_end(lines)
    assert 1 < cut["line_end"] < len(lines)
    assert _send(client, conv_id, "tóm tắt", {"artifact_id": art, "selection": cut}) == "done"
    where = PICK_LINES.format(span=line_span(1, cut["line_end"]), version=1)
    assert CANVAS_NOTE_PICK.format(title="Ghi chú của người", id=art, where=where) in (
        store.history(conv_id)[0].context
    )


def test_a_cut_that_kept_the_end_line_of_the_whole_selection_is_placed_by_its_text(
    client, store: Store
):
    # Why the web lowers the end line when it cuts: the lines the note was told of would run
    # past the passage, and the note could say nothing of where it is.
    conv_id = client.post("/api/conversations", json={"title": "Dài"}).json()["id"]
    art, lines = _long_canvas(store, conv_id)
    cut = {**_cut_at_a_line_end(lines), "line_end": len(lines)}
    assert _send(client, conv_id, "tóm tắt", {"artifact_id": art, "selection": cut}) == "done"
    context = store.history(conv_id)[0].context
    assert PICK_TEXT.format(version=1) in context
    for end in (cut["line_end"], len(lines)):
        assert PICK_LINES.format(span=line_span(1, end), version=1) not in context
