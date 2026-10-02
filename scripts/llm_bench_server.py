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

from my_agent_crew.tools.shell import PASSTHROUGH_ENV

# All a server started here gets of the caller's environment: what a program needs to run (what
# a shell command gets, the rest of the locale, the login name, the time zone) and the one model
# key. Whatever else the caller exports stays out, since the server and every hook and command
# it runs would hold it: the live home, its routes and settings, a shell allow list (a command
# would run unasked), a bot token (a second poller would steal the live agent's updates), the
# key or address of another service (one model's run would differ from another's), an agent
# socket.
PASSED_ENV = frozenset({*PASSTHROUGH_ENV, "LOGNAME", "TZ", "OPENROUTER_API_KEY"})
PASSED_PREFIX = "LC_"
STARTUP_SECONDS = 60


def port_is_free(port: int) -> bool:
    with socket.socket() as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


class Server:
    """One `python -m my_agent_crew` on its own home and port. It logs into `log_path`, by
    default `server.log` in the home. `extra_args` and `extra_env` add to its command line and
    environment."""

    def __init__(
        self,
        repo: Path,
        home: Path,
        port: int,
        *,
        extra_args: Sequence[str] = (),
        extra_env: Mapping[str, str] | None = None,
        log_path: Path | None = None,
    ) -> None:
        self.repo, self.home, self.port = repo, home, port
        self.base = f"http://127.0.0.1:{port}/api"
        self.log_path = log_path or home / "server.log"
        self._extra_args = tuple(extra_args)
        self._extra_env = dict(extra_env or {})
        self._proc: subprocess.Popen[bytes] | None = None
        self._log: IO[bytes] | None = None

    def command(self) -> list[str]:
        return [sys.executable, "-m", "my_agent_crew", "--port", str(self.port), *self._extra_args]

    def environment(self, caller: Mapping[str, str] | None = None) -> dict[str, str]:
        """What `caller`, this process's environment by default, holds of `PASSED_ENV`, then
        the server's home and `extra_env`."""
        source = os.environ if caller is None else caller
        env = {k: v for k, v in source.items() if k in PASSED_ENV or k.startswith(PASSED_PREFIX)}
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
