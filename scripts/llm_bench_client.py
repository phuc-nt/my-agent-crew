"""The bench's view of one server: start it on a throwaway home, talk to it over the HTTP
API the web uses, stop it. Nothing here knows about the live home or the live port; the
server is a child of this process and dies with it."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

import httpx

# What the bench must not inherit: the live home, the live routes, the Telegram bot (a
# second poller would steal the live agent's updates) and every optional backend that
# would make one model's run differ from another's.
DROPPED_ENV = (
    "MY_AGENT_HOME",
    "MY_AGENT_ROUTES",
    "MY_AGENT_OPENROUTER_PROVIDERS",
    "MY_AGENT_OPENROUTER_PROVIDER_FALLBACKS",
    "TELEGRAM_BOT_TOKEN",
    "OLLAMA_BASE_URL",
    "FIRECRAWL_BASE_URL",
    "FIRECRAWL_API_KEY",
    "BRAVE_API_KEY",
    "TAVILY_API_KEY",
)
STARTUP_SECONDS = 60


def port_is_free(port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


class Server:
    """One `python -m my_agent_crew` on its own home and port, logged into that home."""

    def __init__(self, repo: Path, home: Path, port: int) -> None:
        self.repo, self.home, self.port = repo, home, port
        self.base = f"http://127.0.0.1:{port}/api"
        self._proc: subprocess.Popen[bytes] | None = None
        self._log: IO[bytes] | None = None

    def start(self) -> None:
        if not port_is_free(self.port):
            raise SystemExit(f"port {self.port} is busy: stop its owner first, it is not mine")
        env = {k: v for k, v in os.environ.items() if k not in DROPPED_ENV}
        env["MY_AGENT_HOME"] = str(self.home)
        self._log = open(self.home / "server.log", "ab")
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "my_agent_crew", "--port", str(self.port)],
            cwd=self.repo,
            env=env,
            stdout=self._log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + STARTUP_SECONDS
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise SystemExit(f"server exited early, see {self.home / 'server.log'}")
            try:
                httpx.get(f"{self.base}/agents", timeout=2.0).raise_for_status()
                return
            except httpx.HTTPError:
                time.sleep(0.5)
        self.stop()
        raise SystemExit(f"server did not come up in {STARTUP_SECONDS}s")

    def stop(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(5)
        if self._log is not None:
            self._log.close()
        self._proc, self._log = None, None


@dataclass
class Turn:
    answer: str = ""
    events: list[str] = field(default_factory=list)
    approvals: int = 0
    wall_s: float = 0.0
    error: str = ""


class Api:
    def __init__(self, base: str, timeout: float) -> None:
        self._client = httpx.Client(base_url=base, timeout=httpx.Timeout(timeout, connect=5.0))

    def create_conversation(self, agent_id: str = "default") -> str:
        resp = self._client.post("/conversations", json={"agent_id": agent_id})
        resp.raise_for_status()
        return str(resp.json()["id"])

    def turn(self, conv_id: str, text: str) -> Turn:
        """One user message, followed through every approval the turn asks for, until the
        stream that ends the turn closes. A question to the person is a failure: the bench
        has nobody to answer it."""
        turn = Turn()
        start = time.monotonic()
        path, body = f"/conversations/{conv_id}/messages", {"text": text}
        try:
            while True:
                pending = self._consume(path, body, turn)
                if pending is None or turn.error:
                    break
                turn.approvals += 1
                path, body = f"/conversations/{conv_id}/approvals/{pending}", {"approve": True}
        except httpx.HTTPError as exc:
            turn.error = f"http: {exc}"
        turn.wall_s = round(time.monotonic() - start, 2)
        return turn

    def _consume(self, path: str, body: dict[str, Any], turn: Turn) -> str | None:
        pending: str | None = None
        event = ""
        with self._client.stream("POST", path, json=body) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line.startswith("event:"):
                    event = line[len("event:") :].strip()
                elif line.startswith("data:") and event:
                    data = json.loads(line[len("data:") :])
                    self._note(event, data, turn)
                    if event == "approval_required":
                        pending = self._pending(data, turn)
                    event = ""
        return pending or None

    @staticmethod
    def _pending(data: dict[str, Any], turn: Turn) -> str | None:
        if data.get("kind") == "question":
            turn.error = "asked the person a question"
            return None
        return str(data["approval_id"])

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
