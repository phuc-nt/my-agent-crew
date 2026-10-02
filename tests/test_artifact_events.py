"""Every change to a canvas is announced on the activity stream, so an open panel follows it:
made, saved, renamed, restored or deleted over REST, written by an agent's tool, or written by
a thread other than the one the watchers wait on."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agents.profile import DEFAULT_AGENT_ID
from my_agent_crew.config import DEFAULT_TOOL_OUTPUT_CHARS, Route
from my_agent_crew.server import create_app
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store.artifact_versions import COALESCE_WINDOW_S
from my_agent_crew.store.db import Store
from my_agent_crew.tools.artifact import build_artifact_tools
from tests.canvas_helpers import ZONE, agents_canvas
from tests.test_server_api import parse_sse


@pytest.fixture
async def served(deps_factory, store: Store):
    """The app on the test's own loop, built through `Runtime.single` the way tests build it,
    with the canvas tools so the offline model can write one."""
    tools = build_artifact_tools(store, DEFAULT_AGENT_ID, False, DEFAULT_TOOL_OUTPUT_CHARS, ZONE)
    runtime = Runtime.single(deps_factory(routes=(Route("fake", "echo"),), extra_tools=tools))
    transport = httpx.ASGITransport(app=create_app(runtime, schedule=False))
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        yield client, runtime
    await runtime.drain.stop()


async def _watching(hub: ActivityHub) -> AsyncIterator[dict[str, Any]]:
    stream = hub.subscribe()
    assert (await anext(stream))["type"] == "snapshot"
    return stream


async def _next_artifact(stream: AsyncIterator[dict[str, Any]]) -> dict[str, Any]:
    while True:
        payload = await asyncio.wait_for(anext(stream), 2)
        if payload["type"] == "artifact":
            return payload


def _as_stored(store: Store, art: str, conversation_ids: list[str]) -> dict[str, Any]:
    """The event for `art` as the store holds it now."""
    summary = store.artifacts.get(art).to_dict()
    return {"type": "artifact", "artifact": summary, "conversation_ids": conversation_ids}


async def test_every_change_made_over_rest_is_announced(served, canvas_clock):
    client, runtime = served
    store = runtime.store
    conv = store.create()
    stream = await _watching(runtime.hub)
    sent = {"title": "Kế hoạch", "kind": "markdown", "content": "# a", "conversation_id": conv.id}
    art = (await client.post("/api/artifacts", json=sent)).json()["id"]
    assert await _next_artifact(stream) == _as_stored(store, art, [])

    canvas_clock.tick(COALESCE_WINDOW_S + 1)  # so the save keeps version 1 to restore
    await client.put(f"/api/artifacts/{art}", json={"content": "# b", "base_version": 1})
    assert await _next_artifact(stream) == _as_stored(store, art, [conv.id])
    assert store.artifacts.get(art).head_version == 2

    await client.patch(f"/api/artifacts/{art}", json={"title": "Kế hoạch mới"})
    assert await _next_artifact(stream) == _as_stored(store, art, [conv.id])
    renamed = store.artifacts.get(art)
    assert (renamed.head_version, renamed.title) == (2, "Kế hoạch mới")

    await client.post(f"/api/artifacts/{art}/restore", json={"version": 1})
    assert await _next_artifact(stream) == _as_stored(store, art, [conv.id])
    assert store.artifacts.get(art).head_version == 3

    await client.delete(f"/api/artifacts/{art}")
    gone = {"type": "artifact", "artifact": {"id": art, "deleted": True}}
    assert await _next_artifact(stream) == {**gone, "conversation_ids": [conv.id]}


async def test_a_canvas_an_agent_writes_with_its_tool_is_announced(served):
    client, runtime = served
    conv_id = (await client.post("/api/conversations", json={"title": "Thử"})).json()["id"]
    stream = await _watching(runtime.hub)
    call = '/tool artifact_create {"title": "Kế hoạch", "kind": "markdown", "content": "# a"}'
    response = await client.post(f"/api/conversations/{conv_id}/messages", json={"text": call})
    assert parse_sse(response.text)[-1]["type"] == "done"
    [made] = runtime.store.artifacts.list()
    assert await _next_artifact(stream) == _as_stored(runtime.store, made.id, [])
    assert (made.agent_id, made.head_version) == (DEFAULT_AGENT_ID, 1)


def test_a_write_from_another_thread_reaches_the_watchers_loop(store: Store, caplog):
    """The loop runs in debug mode, which refuses a callback scheduled on it from the wrong
    thread: a payload put straight into a watcher's queue from the writer's thread would be
    logged as a failing listener and never wake the watcher. Such a watcher cannot be
    cancelled either, so the loop is closed by hand: `asyncio.run` would wait on it for good."""
    hub = ActivityHub(store)
    store.artifacts.on_change = hub.publish_artifact
    art = agents_canvas(store, "coach", "# a")

    async def main() -> dict[str, Any] | None:
        stream = await _watching(hub)
        waiting = asyncio.ensure_future(anext(stream))
        await asyncio.sleep(0)  # the watcher now waits on its queue
        await asyncio.to_thread(store.artifacts.write, art, "# b", "agent:coach", "")
        done, _ = await asyncio.wait({waiting}, timeout=0.5)
        if not done:
            return None
        await stream.aclose()
        return waiting.result()

    loop = asyncio.new_event_loop()
    loop.set_debug(True)
    with caplog.at_level(logging.DEBUG):
        try:
            payload = loop.run_until_complete(main())
        finally:
            loop.close()
    assert payload == _as_stored(store, art, [])
    assert store.artifacts.get(art).head_version == 2
    assert not [record for record in caplog.records if "a listener failed" in record.message]
    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
