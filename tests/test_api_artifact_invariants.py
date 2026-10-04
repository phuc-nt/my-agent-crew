"""What holds across the canvas routes. Each runs on the event loop: a route FastAPI hands to
its thread pool would write the store, and announce the change, from a thread the watchers do
not wait on. And reading changes nothing: no GET moves what a conversation has seen, read,
been told or shared, nor what it has open."""

from __future__ import annotations

import inspect

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from my_agent_crew.server import (
    create_app,
    routes_artifact_history,
    routes_artifact_import,
    routes_artifact_render,
    routes_artifacts,
    routes_canvas_focus,
    routes_chat,
)
from my_agent_crew.server.app import ROUTERS as SERVED
from my_agent_crew.store.db import Store
from tests.canvas_helpers import PLAN, SWIM, agents_canvas

ROUTERS = (
    routes_artifacts.router,
    routes_artifact_history.router,
    routes_artifact_import.router,
    routes_artifact_render.router,
    routes_canvas_focus.router,
)
PICK = {"version": 2, "text": "bơi 1 km", "line_start": 3, "line_end": 3}


@pytest.fixture
def client(deps_factory):
    app = create_app(deps_factory(), schedule=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client


def test_every_canvas_route_and_the_chat_message_run_on_the_event_loop():
    routes = [route for router in ROUTERS for route in router.routes]
    assert all(isinstance(route, APIRoute) for route in routes)
    endpoints = [route.endpoint for route in routes] + [routes_chat.post_message]
    assert len(endpoints) >= 12
    assert [e.__name__ for e in endpoints if not inspect.iscoroutinefunction(e)] == []


def test_the_routers_checked_here_are_every_canvas_router_the_app_serves():
    """A canvas router added to the app and not to the list above would go unchecked."""
    canvas = [
        router
        for router in SERVED
        if any("artifact" in route.path or "canvas" in route.path for route in router.routes)
    ]
    assert len(canvas) == len(ROUTERS) == len(set(map(id, ROUTERS)))
    assert all(any(router is checked for checked in ROUTERS) for router in canvas)


def _state(store: Store, conv_id: str, art: str) -> tuple:
    """Everything a read could move: the link with its cursors, the open canvas with its
    selection, the canvas and its versions, and the conversation's messages."""
    versions = [version.meta() for version in store.artifacts.versions(art)]
    return (
        store.artifact_links.get(conv_id, art),
        store.artifact_links.focus(conv_id),
        store.artifacts.get(art),
        versions,
        store.history(conv_id),
    )


READS = [
    "/api/artifacts",
    "/api/artifacts?conversation_id={conv}",
    "/api/artifacts/{art}",
    "/api/artifacts/{art}/versions",
    "/api/artifacts/{art}/versions/1",
    "/api/artifacts/{art}/raw",
    "/api/artifacts/{art}/raw?version=1&download=1",
    "/api/conversations/{conv}/canvas",
]
# The page of a canvas that runs, as the newest version and as an earlier one.
PAGES = ["/api/artifacts/{art}/render", "/api/artifacts/{art}/render?version=1"]


@pytest.mark.parametrize(
    ("path", "kind"),
    [(path, "markdown") for path in READS]
    + [(path, kind) for path in PAGES for kind in ("html", "mermaid")],
)
def test_no_read_changes_what_a_conversation_knows_or_has_open(client, store: Store, path, kind):
    conv, art = store.create(), agents_canvas(store, "coach", PLAN, kind)
    store.artifacts.write(art, SWIM, "agent:coach", conv.id)
    links = store.artifact_links
    links.link(conv.id, art, shared=True)
    links.mark_seen(conv.id, art, 1)
    links.mark_read(conv.id, art, 2, 0, 5, len(SWIM))  # a paged read, part way through
    links.mark_noted(conv.id, art, 2)
    links.set_focus(conv.id, art, PICK)
    links.note_focus(conv.id)
    before = _state(store, conv.id, art)
    assert (before[0].read_upto, before[1].noted, before[1].selection) == (5, True, PICK)
    response = client.get(path.format(conv=conv.id, art=art))
    assert response.status_code == 200, response.text
    assert _state(store, conv.id, art) == before
