"""Every response forbids another site framing it, so a page elsewhere cannot lay the app under
its own buttons and have the person click Approve. A policy a route sets for itself is left as it
is, and an event stream still reaches the client while it is open."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.types import Message

from my_agent_crew.server import create_app
from my_agent_crew.server.app import STATIC_DIR
from tests.canvas_helpers import PLAN, agents_canvas

NO_FRAMING = "frame-ancestors 'self'"
RAW_POLICY = "default-src 'none'; style-src 'unsafe-inline'; sandbox"


@pytest.fixture
def app(deps_factory):
    return create_app(deps_factory(), schedule=False)


def _policies(response) -> list[str]:
    return response.headers.get_list("content-security-policy")


def test_the_page_the_api_an_asset_and_a_404_all_forbid_framing(app):
    asset = next((STATIC_DIR / "assets").glob("*.js")).name
    answers = [
        ("/", 200),
        ("/conversations/abc", 200),
        ("/api/health", 200),
        (f"/assets/{asset}", 200),
        ("/api/definitely-not-a-route", 404),
        ("/assets/nothing-here.js", 404),
    ]
    with TestClient(app, base_url="http://127.0.0.1") as client:
        for path, status in answers:
            response = client.get(path)
            assert response.status_code == status, path
            assert _policies(response) == [NO_FRAMING], path


def test_a_refusal_of_the_local_guard_forbids_framing_too(app):
    with TestClient(app, base_url="http://evil.example:8765") as rebound:
        response = rebound.get("/api/health")
    assert response.status_code == 403
    assert _policies(response) == [NO_FRAMING]


def test_the_500_page_of_an_error_nothing_caught_forbids_framing_too(app):
    def explode() -> None:
        raise RuntimeError("no handler takes this")

    # In front of the catch-all that answers every address the API does not own with the page.
    app.router.routes.insert(0, APIRoute("/api/explodes", explode))
    with TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False) as client:
        response = client.get("/api/explodes")
    assert response.status_code == 500
    assert response.text == "Internal Server Error"
    assert _policies(response) == [NO_FRAMING]


def test_a_policy_a_route_sets_itself_stays_and_the_rule_is_a_second_header(app, store):
    art = agents_canvas(store, "coach", PLAN)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        raw = client.get(f"/api/artifacts/{art}/raw")
    assert raw.status_code == 200
    assert _policies(raw) == [RAW_POLICY, NO_FRAMING]


async def test_an_event_stream_delivers_its_first_event_while_it_is_still_open(app):
    sent: list[Message] = []
    first_event = asyncio.Event()
    hang_up = asyncio.Event()

    async def receive() -> Message:
        await hang_up.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)
        if message["type"] == "http.response.body" and b"snapshot" in message.get("body", b""):
            first_event.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/activity/stream",
        "raw_path": b"/api/activity/stream",
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"127.0.0.1")],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 80),
    }
    serving = asyncio.create_task(app(scope, receive, send))
    try:
        await asyncio.wait_for(first_event.wait(), timeout=5)
        assert not serving.done(), "the stream ended instead of staying open"
        start = next(m for m in sent if m["type"] == "http.response.start")
        assert (b"content-security-policy", NO_FRAMING.encode()) in start["headers"]
    finally:
        hang_up.set()
        await asyncio.wait_for(serving, timeout=5)
