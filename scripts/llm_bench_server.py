"""The bench's server: one `python -m my_agent_crew` on its own home and port. Nothing here
knows about the live home or the live port; the server is a child of this process and dies
with it."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import IO

import httpx

# What the bench must not inherit: the live home, the live routes, a shell allow list (a
# command would run unasked), the Telegram bot (a second poller would steal the live agent's
# updates) and every optional backend that would make one model's run differ from another's.
DROPPED_ENV = (
    "MY_AGENT_HOME",
    "MY_AGENT_ROUTES",
    "MY_AGENT_SHELL_ALLOW_PATTERNS",
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
    """One `python -m my_agent_crew` on its own home and port. It logs into `log_path`, by
    default `server.log` in the home. `extra_args` and `extra_env` add to its command line and
    environment; `dropped_env` names more variables to keep from it than the bench does."""

    def __init__(
        self,
        repo: Path,
        home: Path,
        port: int,
        *,
        extra_args: Sequence[str] = (),
        extra_env: Mapping[str, str] | None = None,
        dropped_env: Sequence[str] = (),
        log_path: Path | None = None,
    ) -> None:
        self.repo, self.home, self.port = repo, home, port
        self.base = f"http://127.0.0.1:{port}/api"
        self.log_path = log_path or home / "server.log"
        self._extra_args = tuple(extra_args)
        self._extra_env = dict(extra_env or {})
        self._dropped = {*DROPPED_ENV, *dropped_env}
        self._proc: subprocess.Popen[bytes] | None = None
        self._log: IO[bytes] | None = None

    def command(self) -> list[str]:
        return [sys.executable, "-m", "my_agent_crew", "--port", str(self.port), *self._extra_args]

    def environment(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if k not in self._dropped}
        env["MY_AGENT_HOME"] = str(self.home)
        env.update(self._extra_env)
        return env

    def start(self) -> None:
        if not port_is_free(self.port):
            raise SystemExit(f"port {self.port} is busy: stop its owner first, it is not mine")
        self._log = open(self.log_path, "ab")
        self._proc = subprocess.Popen(
            self.command(),
            cwd=self.repo,
            env=self.environment(),
            stdout=self._log,
            stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + STARTUP_SECONDS
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise SystemExit(f"server exited early, see {self.log_path}")
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
