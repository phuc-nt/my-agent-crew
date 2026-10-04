"""What reading a canvas's workspace file again leaves alone, and whom it tells. It links no
conversation and makes nothing seen: the person pressed the button, no agent read the result.
Which file is read is the canvas's to say, never the request's, and nothing the web sends
gives a canvas a file to read. A change is announced like any other write; no change, no
event."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from my_agent_crew.agents.profile import DEFAULT_AGENT_ID
from my_agent_crew.config import Route
from my_agent_crew.server import create_app
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store.artifact_models import IMPORT_NOTE, USER
from my_agent_crew.store.db import Store
from my_agent_crew.texts_canvas import REIMPORT_NO_SOURCE
from tests.canvas_helpers import PLAN, SWIM, put
from tests.test_api_artifact_import import FILE, SOURCE, imported, reimport


@pytest.fixture
def served(deps_factory) -> Iterator[tuple[TestClient, Path]]:
    """The app, and the default agent's workspace with FILE changed since it was imported."""
    deps = deps_factory()
    put(deps.agent.workspace, FILE, SWIM)
    with TestClient(create_app(deps, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, deps.agent.workspace


def test_a_reimport_links_no_conversation_and_makes_nothing_seen(served, store: Store):
    client, _ = served
    art = imported(store)
    linked, other = store.create(), store.create()
    store.artifact_links.mark_seen(linked.id, art, 1)
    before = store.artifact_links.get(linked.id, art)
    assert reimport(client, art).json()["changed"] is True
    assert store.artifacts.head(art).conversation_id == ""
    assert store.artifact_links.conversations_for(art) == [linked.id]
    assert store.artifact_links.get(linked.id, art) == before
    assert before is not None and before.seen_version == 1
    assert store.artifact_links.get(other.id, art) is None


def test_the_request_picks_neither_the_file_nor_whose_version_it_becomes(served, store: Store):
    client, root = served
    art = imported(store)
    conv = store.create()
    put(root, "notes/other.md", "khác\n")
    aimed = {
        "path": "notes/other.md",
        "source": f"workspace:{DEFAULT_AGENT_ID}/notes/other.md",
        "conversation_id": conv.id,
        "kind": "html",
        "author": "agent:coach",
        "note": "",
        "content": "khác\n",
    }
    assert reimport(client, art, **aimed).json()["changed"] is True
    summary, head = store.artifacts.get(art), store.artifacts.head(art)
    assert (head.content, head.author, head.note, head.conversation_id) == (
        SWIM,
        USER,
        IMPORT_NOTE,
        "",
    )
    assert (summary.source, summary.kind) == (SOURCE, "markdown")
    assert store.artifact_links.conversations_for(art) == []


def test_no_request_of_the_web_gives_a_canvas_a_source(served, store: Store):
    """Only an agent's import records one, so a page cannot aim a re-import at a file."""
    client, _ = served
    sent = {"title": "Kế hoạch", "kind": "markdown", "content": PLAN, "source": SOURCE}
    art = client.post("/api/artifacts", json=sent).json()["id"]
    saved = {"content": SWIM, "base_version": 1, "source": SOURCE}
    assert client.put(f"/api/artifacts/{art}", json=saved).status_code == 200
    renamed = {"title": "Kế hoạch tuần", "source": SOURCE}
    assert client.patch(f"/api/artifacts/{art}", json=renamed).status_code == 200
    assert store.artifacts.get(art).source == ""
    refused = reimport(client, art)
    assert (refused.status_code, refused.json()["detail"]) == (422, REIMPORT_NO_SOURCE)


async def test_a_reimport_is_announced_only_when_it_changed_the_canvas(deps_factory, store: Store):
    """The event goes to the conversations the canvas is linked to, like any other write."""
    deps = deps_factory(routes=(Route("fake", "echo"),))
    runtime = Runtime.single(deps)
    put(deps.agent.workspace, FILE, PLAN)
    art, conv = imported(store), store.create()
    store.artifact_links.link(conv.id, art)
    transport = httpx.ASGITransport(app=create_app(runtime, schedule=False))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        stream = runtime.hub.subscribe()
        assert (await anext(stream))["type"] == "snapshot"
        same = await client.post(f"/api/artifacts/{art}/reimport", json={"base_version": 1})
        assert same.json()["changed"] is False
        put(deps.agent.workspace, FILE, SWIM)
        changed = await client.post(f"/api/artifacts/{art}/reimport", json={"base_version": 1})
        event = await asyncio.wait_for(anext(stream), 2)
        while event["type"] != "artifact":
            event = await asyncio.wait_for(anext(stream), 2)
    await runtime.drain.stop()
    summary = changed.json()["artifact"]
    assert event == {"type": "artifact", "artifact": summary, "conversation_ids": [conv.id]}
    assert summary["head_version"] == 2
