"""A scripted stand-in for the server's HTTP API, for the clients that talk to it: each path
answers from its own queue of replies, and every request is kept for the test to read."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx

Event = tuple[str, dict[str, Any]]
Reply = httpx.Response | Callable[[], httpx.Response]


def sse(*events: Event) -> httpx.Response:
    body = "".join(f"event: {kind}\r\ndata: {json.dumps(data)}\r\n\r\n" for kind, data in events)
    return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})


def held(gate: threading.Event, *events: Event) -> httpx.Response:
    """A stream that sends keep-alives, as the server's does, until `gate` opens, and then
    says `events` and ends."""

    def body():
        while not gate.is_set():
            yield b": ping\r\n\r\n"
            time.sleep(0.005)
        for kind, data in events:
            yield f"event: {kind}\r\ndata: {json.dumps(data)}\r\n\r\n".encode()

    return httpx.Response(200, content=body(), headers={"content-type": "text/event-stream"})


def opens(gate: threading.Event, reply: httpx.Response) -> Callable[[], httpx.Response]:
    """A reply that opens `gate` the moment it is asked for."""

    def reply_and_open() -> httpx.Response:
        gate.set()
        return reply

    return reply_and_open


def say(text: str) -> Event:
    return "assistant_message", {"content": text}


def tool_approval(approval_id: str, name: str = "shell_run", **arguments: Any) -> Event:
    return "approval_required", {
        "approval_id": approval_id,
        "tool_call_id": f"call-{approval_id}",
        "name": name,
        "arguments": arguments,
        "kind": "tool",
    }


def question(approval_id: str, text: str = "which one?") -> Event:
    return "approval_required", {
        "approval_id": approval_id,
        "tool_call_id": f"call-{approval_id}",
        "name": "ask_user",
        "arguments": {"question": text},
        "kind": "question",
        "options": [],
    }


def as_json(data: Any) -> httpx.Response:
    return httpx.Response(200, json=data)


class FakeServer:
    """A reply is a response, or a function that makes one when the request arrives. A path
    takes its queued replies in order, then its standing reply."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self._replies: dict[str, list[Reply]] = {}
        self._standing: dict[str, Reply] = {}
        self._lock = threading.Lock()
        self.transport = httpx.MockTransport(self._handle)

    def on(self, path: str, *replies: Reply) -> FakeServer:
        self._replies.setdefault(path, []).extend(replies)
        return self

    def always(self, path: str, reply: Reply) -> FakeServer:
        self._standing[path] = reply
        return self

    def posted(self) -> list[str]:
        """The paths asked for, in order."""
        with self._lock:
            return [path for path, _body in self.requests]

    def body_of(self, path: str) -> dict[str, Any]:
        with self._lock:
            return next(body for seen, body in self.requests if seen == path)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        with self._lock:
            self.requests.append((path, body))
            queue = self._replies.get(path)
            reply = queue.pop(0) if queue else self._standing[path]
        return reply() if callable(reply) else reply
