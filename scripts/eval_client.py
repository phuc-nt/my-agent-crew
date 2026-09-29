"""The eval runner's view of a conversation: the bench's HTTP client, plus what a case decides
about the approvals and questions its turns run into, plus the server's cost ledger."""

from __future__ import annotations

import json
import threading
from collections.abc import Sequence
from typing import Any

import httpx
from llm_bench_client import HTTP_FAILED, Api, Step, Turn

POLL_SECONDS = 0.5
WATCH_JOIN_SECONDS = 30.0
AWAITING = "awaiting_approval"
NO_ANSWER = "asked the person a question and the case has no answer left"


def as_event(pending: dict[str, Any]) -> dict[str, Any]:
    """A pending approval as `GET /conversations/<id>` lists it, in the shape of the stream
    event that would have carried it."""
    return {
        "approval_id": pending["id"],
        "name": pending["tool_name"],
        "arguments": pending["arguments"],
        "kind": pending["kind"],
    }


class EvalApi(Api):
    """`start_case` sets how the next case answers; every tool approval it meets is kept in
    `asked`, with the turn it came in (counting from 1), for the case's expectations. Turns
    also answer what agents the master delegated to ask, in conversations of their own."""

    def __init__(
        self,
        base: str,
        timeout: float,
        live_paths: Sequence[str] = (),
        transport: httpx.BaseTransport | None = None,
        turn_seconds: float | None = None,
    ) -> None:
        super().__init__(base, timeout, transport, turn_seconds)
        self._live = tuple(path.lower() for path in live_paths)
        self.policy = "deny"
        self.answers: list[str] = []
        self.asked: list[dict[str, Any]] = []
        self._turn_no = 0
        self._abort = ""
        self._lock = threading.Lock()

    def start_case(self, policy: str, answers: Sequence[str]) -> None:
        self.policy, self.answers = policy, list(answers)
        self.asked, self._turn_no, self._abort = [], 0, ""

    def turn(self, conv_id: str, text: str) -> Turn:
        self._turn_no += 1
        stop = threading.Event()
        watcher = threading.Thread(target=self._watch_children, args=(conv_id, stop), daemon=True)
        watcher.start()
        try:
            turn = super().turn(conv_id, text)
        finally:
            stop.set()
            watcher.join(WATCH_JOIN_SECONDS)
        if self._abort and not turn.error:
            turn.error = self._abort
        return turn

    def _cut_short(self) -> str:
        return self._abort or super()._cut_short()

    def _answer(self, conv_id: str, pending: dict[str, Any], turn: Turn) -> Step | None:
        base = f"/conversations/{conv_id}/approvals/{pending['approval_id']}"
        with self._lock:
            if pending.get("kind") == "question":
                if not self.answers:
                    self._abort = turn.error = NO_ANSWER
                    return None
                return f"{base}/answer", {"answer": self.answers.pop(0)}
            self.asked.append({**pending, "turn": self._turn_no})
        turn.approvals += 1
        return base, {"approve": self.policy == "approve" and not self._names_live_path(pending)}

    def _names_live_path(self, pending: dict[str, Any]) -> bool:
        """An approved command could read or change the live tree if it spells its path out."""
        arguments = json.dumps(pending.get("arguments") or {}, ensure_ascii=False).lower()
        return any(path in arguments for path in self._live)

    def _watch_children(self, conv_id: str, stop: threading.Event) -> None:
        """Answers what a delegated child asks. It asks in its own conversation, which the
        parent's stream never carries: the parent only waits, sending keep-alives, until the
        child is done. A failure here ends the turn, or it would wait out its whole time."""
        try:
            while not stop.wait(POLL_SECONDS):
                for child in self._awaiting_children(conv_id):
                    pending = self.conversation(child).get("pending_approval")
                    if pending:
                        self._answer_child(child, pending)
        except httpx.HTTPError as exc:
            self._abort = f"{HTTP_FAILED} {exc}"
        except (KeyError, ValueError) as exc:
            self._abort = f"could not read what a delegated child waits on: {exc!r}"

    def _awaiting_children(self, conv_id: str) -> list[str]:
        awaiting = {
            run["conversation_id"]
            for run in self.runs(conv_id)
            if run["conversation_id"] != conv_id and run["status"] == AWAITING
        }
        return sorted(awaiting)

    def _answer_child(self, child: str, pending: dict[str, Any]) -> None:
        turn = Turn()
        self._drive(child, self._answer(child, as_event(pending), turn), turn)
        if turn.error.startswith(HTTP_FAILED):
            self._abort = turn.error

    def agent_ids(self) -> list[str]:
        resp = self._client.get("/agents")
        resp.raise_for_status()
        return [str(agent["id"]) for agent in resp.json()]

    def ledger(self) -> tuple[float, int]:
        """What the server has spent since it started: dollars, and the calls whose price the
        provider did not give (so the dollars are a lower bound when there are any)."""
        resp = self._client.get("/stats")
        resp.raise_for_status()
        purposes = resp.json().get("purposes") or []
        cost = sum(float(p.get("cost_usd") or 0.0) for p in purposes)
        return cost, sum(int(p.get("unknown_cost_calls") or 0) for p in purposes)
