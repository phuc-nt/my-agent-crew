"""The bench's view of one server, over the HTTP API the web uses: a turn, followed through
every approval it stops on."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

Step = tuple[str, dict[str, Any]]  # the next request of a turn: (path, JSON body)

TIMED_OUT = "timed out after"
HTTP_FAILED = "http:"  # what a turn error starts with when the server could not be reached


@dataclass
class Turn:
    answer: str = ""
    events: list[str] = field(default_factory=list)
    approvals: int = 0
    wall_s: float = 0.0
    error: str = ""


class Api:
    def __init__(
        self,
        base: str,
        timeout: float,
        transport: httpx.BaseTransport | None = None,
        turn_seconds: float | None = None,
    ) -> None:
        """`timeout` bounds each wait on the server; `turn_seconds`, when given, bounds a whole
        turn, which a stream that keeps sending keep-alives would otherwise never reach."""
        self._client = httpx.Client(
            base_url=base, timeout=httpx.Timeout(timeout, connect=5.0), transport=transport
        )
        self._turn_seconds = turn_seconds
        self._deadline: float | None = None

    def create_conversation(self, agent_id: str = "default", autonomous: bool | None = None) -> str:
        body: dict[str, Any] = {"agent_id": agent_id}
        if autonomous is not None:
            body["autonomous"] = autonomous
        resp = self._client.post("/conversations", json=body)
        resp.raise_for_status()
        return str(resp.json()["id"])

    def turn(self, conv_id: str, text: str) -> Turn:
        """One user message, followed through every approval the turn asks for, until the
        stream that ends the turn closes."""
        turn = Turn()
        start = time.monotonic()
        self._deadline = start + self._turn_seconds if self._turn_seconds else None
        self._drive(conv_id, (f"/conversations/{conv_id}/messages", {"text": text}), turn)
        turn.wall_s = round(time.monotonic() - start, 2)
        return turn

    def _drive(self, conv_id: str, step: Step | None, turn: Turn) -> None:
        """Follows `step`, and each approval its stream stops on, until a stream ends clean."""
        try:
            while step is not None:
                pending = self._consume(*step, turn)
                if pending is None or turn.error:
                    break
                step = self._answer(conv_id, pending, turn)
        except httpx.HTTPError as exc:
            turn.error = f"{HTTP_FAILED} {exc}"

    def _cut_short(self) -> str:
        """Why the turn in flight must stop now, or an empty string. Checked as each line of
        a stream arrives, and a stream that keeps sending keep-alives never times out itself."""
        if self._deadline is not None and time.monotonic() > self._deadline:
            return f"{TIMED_OUT} {self._turn_seconds:g}s"
        return ""

    def _answer(self, conv_id: str, pending: dict[str, Any], turn: Turn) -> Step | None:
        """The request that answers an approval the turn stopped on, or None to end the turn.
        The bench approves every tool; a question to the person is a failure, it has nobody
        to answer it."""
        if pending.get("kind") == "question":
            turn.error = "asked the person a question"
            return None
        turn.approvals += 1
        return f"/conversations/{conv_id}/approvals/{pending['approval_id']}", {"approve": True}

    def _consume(self, path: str, body: dict[str, Any], turn: Turn) -> dict[str, Any] | None:
        pending: dict[str, Any] | None = None
        event = ""
        with self._client.stream("POST", path, json=body) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                reason = self._cut_short()
                if reason:
                    turn.error = reason
                    break
                if line.startswith("event:"):
                    event = line[len("event:") :].strip()
                elif line.startswith("data:") and event:
                    data = json.loads(line[len("data:") :])
                    self._note(event, data, turn)
                    if event == "approval_required":
                        pending = data
                    event = ""
        return pending

    @staticmethod
    def _note(event: str, data: dict[str, Any], turn: Turn) -> None:
        turn.events.append(event)
        if event == "assistant_message" and data.get("content"):
            turn.answer = str(data["content"])
        elif event == "error":
            turn.error = str(data.get("message", "error"))
        elif event == "halted":
            turn.error = f"halted: {data.get('reason', '?')}"

    def conversation(self, conv_id: str) -> dict[str, Any]:
        resp = self._client.get(f"/conversations/{conv_id}")
        resp.raise_for_status()
        return dict(resp.json())

    def runs(self, conv_id: str) -> list[dict[str, Any]]:
        """The conversation's runs and those of what it delegated, oldest first."""
        resp = self._client.get("/activity/runs", params={"conversation_id": conv_id})
        resp.raise_for_status()
        return sorted(resp.json(), key=lambda r: r["started_at"])
