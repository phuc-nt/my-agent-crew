"""Which hosts this process calls, counted per host and per day.

The owner of a crew can ask where it talks to. Every HTTP client the engine makes is built
here (`counted_client`), with a hook that counts the host of each request it sends, a
redirect's hop included; the browsers' proxy counts the host of each connection it opens
(`browser/proxy.py`). A host name is all that is kept: never a path, a query, a header or a
body. Nothing is allowed or refused here.

Counting is a tally in memory, written to the store in batches (`store/egress.py`): when
enough calls have gathered or enough time has passed, on a timer while the server runs, when
the report is read and when the server stops. A count that cannot be kept is dropped and the
request it counted goes on: `count` and `flush` never raise.

What other processes send is not seen: a shell command (curl, git, a CLI) and a hook's
command open their own connections (`NOT_SEEN`).
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BATCH_CALLS = 50
BATCH_SECONDS = 60.0
INVALID = "invalid"
# The ways out of this process's reach, named in the report so no reader takes it for all.
NOT_SEEN = ("shell", "hooks")
_HOST = re.compile(r"[a-z0-9.-]{1,253}")

Counts = dict[tuple[str, str], int]  # (day, host) -> calls
Write = Callable[[Counts, str], None]  # the counts, and the day it is now


def clean_host(raw: object) -> str:
    """The host as it is kept: lowercase, no trailing dot. Whatever is not a host name
    (an IPv6 literal, a name with other characters, nothing at all) is `invalid`."""
    host = raw.strip().lower().removesuffix(".") if isinstance(raw, str) else ""
    return host if _HOST.fullmatch(host) else INVALID


def _utc_today() -> str:
    return datetime.now(UTC).date().isoformat()


class EgressCounter:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._pending: Counts = {}
        self._calls = 0
        self._since = clock()
        self._write: Write | None = None
        self._today: Callable[[], str] = _utc_today

    def bind(self, write: Write, today: Callable[[], str]) -> None:
        """Where the counts are kept and whose day they fall on: the running server's."""
        self._write, self._today = write, today

    def unbind(self, write: Write) -> None:
        """Leaves the store of a server that stopped, unless another has bound since."""
        if self._write == write:
            self._write, self._today = None, _utc_today

    def count(self, host: object) -> None:
        try:
            key = (self._today(), clean_host(host))
            with self._lock:
                self._pending[key] = self._pending.get(key, 0) + 1
                self._calls += 1
                waited = self._clock() - self._since
                due = self._calls >= BATCH_CALLS or waited >= BATCH_SECONDS
            if due:
                self.flush()
        except Exception as exc:
            logger.warning("egress: a call was not counted: %s", exc)

    def flush(self) -> None:
        """Hands what was counted to the store. With no store bound it is dropped, so the
        tally of a process that keeps none stays small."""
        try:
            with self._lock:
                taken, self._pending, self._calls = self._pending, {}, 0
                self._since = self._clock()
            if taken and self._write is not None:
                self._write(taken, self._today())
        except Exception as exc:
            logger.warning("egress: counts were not written: %s", exc)


COUNTER = EgressCounter()


async def count_request(request: httpx.Request) -> None:
    COUNTER.count(request.url.host)


def counted_client(**options: Any) -> httpx.AsyncClient:
    """The one place the engine makes an HTTP client (`tests/test_egress_clients.py` holds
    every source file to it), so none goes out uncounted."""
    hooks = {name: list(held) for name, held in (options.pop("event_hooks", None) or {}).items()}
    hooks["request"] = [*hooks.get("request", []), count_request]
    return httpx.AsyncClient(event_hooks=hooks, **options)


async def flush_loop(counter: EgressCounter = COUNTER, seconds: float = BATCH_SECONDS) -> None:
    """Writes what gathered while no call came to trigger it, until cancelled."""
    while True:
        await asyncio.sleep(seconds)
        counter.flush()
