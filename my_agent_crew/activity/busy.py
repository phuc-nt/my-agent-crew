"""Whether a conversation is busy: a turn of it is running, or about to.

A turn is a generator, so the run it opens starts only when someone reads it. Between the
door handing a turn out and its first read, a second message would find nothing running and
start a second turn beside the first. So the door claims the conversation as it hands a turn
out, and the run's start takes the claim over. A claim nobody takes over — a caller that
never read its stream — lapses after a grace period, so a dropped request cannot hold a
conversation for good.

When a conversation stops being busy, `on_idle` hears of it: that is the queue drain, which
hands the conversation the messages that waited for it."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

# Long enough for a request to reach its first read, short enough that a message queued
# behind an abandoned one does not sit noticeably long.
CLAIM_GRACE_S = 15.0


class Busy:
    def __init__(self, running: Callable[[str], bool], grace: float = CLAIM_GRACE_S):
        """`running` says whether a run of the conversation is under way."""
        self._running = running
        self.grace = grace
        self._claims: dict[str, tuple[float, object]] = {}
        self._timers: dict[str, asyncio.TimerHandle] = {}
        self.on_idle: Callable[[str], None] | None = None

    def claim(self, conv_id: str) -> object:
        """Returns the claim's token: `release` given it drops this claim and no later one."""
        self.release(conv_id)
        token = object()
        self._claims[conv_id] = (time.monotonic(), token)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return token  # no loop to wake anyone; the claim still reads as stale once it is
        self._timers[conv_id] = loop.call_later(self.grace, self._lapse, conv_id)
        return token

    def busy(self, conv_id: str) -> bool:
        claim = self._claims.get(conv_id)
        fresh = claim is not None and time.monotonic() - claim[0] < self.grace
        return fresh or self._running(conv_id)

    def release(self, conv_id: str, token: object | None = None) -> None:
        claim = self._claims.get(conv_id)
        if claim is None or (token is not None and claim[1] is not token):
            return
        del self._claims[conv_id]
        timer = self._timers.pop(conv_id, None)
        if timer is not None:
            timer.cancel()

    def settle(self, conv_id: str) -> None:
        """Tells `on_idle` about a conversation that is no longer busy."""
        if self.on_idle is not None and not self.busy(conv_id):
            self.on_idle(conv_id)

    def _lapse(self, conv_id: str) -> None:
        self.release(conv_id)
        self.settle(conv_id)
