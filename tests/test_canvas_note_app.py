"""The canvas note through the app, the way the web chat sends a message: what the person
changed in a canvas and the canvas open on the web are stored with the message and reach the
model ahead of it. The offline model still calls a canvas tool from a message that carries a
note, so a self-test without a model key can walk every canvas path by hand."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.agents.profile import DEFAULT_AGENT_ID
from my_agent_crew.config import DEFAULT_TOOL_OUTPUT_CHARS, Route
from my_agent_crew.server import create_app
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store
from my_agent_crew.texts_canvas import CANVAS_NOTE_FOCUS
from my_agent_crew.tools.artifact import build_artifact_tools
from tests.canvas_helpers import SWIM, ZONE, edited, framed, seen_canvas
from tests.test_server_api import parse_sse


@pytest.fixture
def client(deps_factory, store: Store):
    tools = build_artifact_tools(store, DEFAULT_AGENT_ID, False, DEFAULT_TOOL_OUTPUT_CHARS, ZONE)
    deps = deps_factory(routes=(Route("fake", "echo"),), extra_tools=tools)
    with TestClient(create_app(deps, schedule=False), base_url="http://127.0.0.1") as client:
        yield client


def _edited_canvas(client: TestClient, store: Store) -> tuple[str, str]:
    """A conversation and its canvas, which the person changed after the agent saw it."""
    conv_id = client.post("/api/conversations", json={"title": "Thử"}).json()["id"]
    art = seen_canvas(store, store.get(conv_id))
    store.artifacts.write(art, SWIM, USER, "")
    return conv_id, art


def _send(client: TestClient, conv_id: str, text: str) -> list[str]:
    response = client.post(f"/api/conversations/{conv_id}/messages", json={"text": text})
    assert response.status_code == 200
    return [event["type"] for event in parse_sse(response.text)]


def test_a_web_message_is_stored_with_the_open_canvas_and_the_change(client, store: Store):
    """The offline model answers with what it read, so its answer shows the note came first."""
    conv_id, art = _edited_canvas(client, store)
    store.artifact_links.set_focus(conv_id, art, None)
    assert _send(client, conv_id, "tiếp nhé")[-1] == "done"
    opened = CANVAS_NOTE_FOCUS.format(title="Kế hoạch", id=art, version=2)
    note = framed(opened, *edited("Kế hoạch", art))
    sent, answer = store.history(conv_id)
    assert (sent.message.content, sent.context) == ("tiếp nhé", note)
    assert answer.message.content == f"(echo) {note}\n\ntiếp nhé"


def test_the_offline_model_calls_a_canvas_tool_from_a_message_with_a_note(client, store: Store):
    conv_id, art = _edited_canvas(client, store)
    assert _send(client, conv_id, f'/tool artifact_read {{"id": "{art}"}}')[-1] == "done"
    sent, called, result, answer = store.history(conv_id)
    assert sent.context == framed(*edited("Kế hoạch", art))
    assert [call.name for call in called.message.tool_calls] == ["artifact_read"]
    assert "bơi 1 km" in result.message.content
    expected = f"Kết quả công cụ artifact_read:\n{result.message.content[:400]}"
    assert answer.message.content == expected
