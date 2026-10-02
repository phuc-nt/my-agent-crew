"""Whoever watches `/api/activity/stream`: one bounded queue per watcher, fed every payload
the hub publishes. A watcher that falls behind is cut off instead of holding the crew's
events in memory, and reconnects to a fresh snapshot.

The queues belong to the event loop the watchers wait on. A payload published from another
thread, such as a canvas written by a route FastAPI runs in its thread pool, is handed to
that loop rather than put into a queue from the wrong thread, which would wake no one."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from typing import Any

# A watcher that falls this many payloads behind is cut off; its stream ends and the
# browser reconnects to a fresh snapshot. One stalled tab must not hold every event of
# every run in memory for as long as it stays open.
SUBSCRIBER_QUEUE_SIZE = 256

Payload = dict[str, Any]


class Watchers:
    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[Payload | None]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def broadcast(self, payload: Payload) -> None:
        """On the watchers' loop, delivers now; from any other thread, hands the payload to
        that loop. Before anyone has watched there is nobody to tell."""
        loop = self._loop
        if loop is None:
            return
        if _running_loop() is loop:
            self._deliver(payload)
            return
        with suppress(RuntimeError):  # the loop has closed with the process
            loop.call_soon_threadsafe(self._deliver, payload)

    def _deliver(self, payload: Payload) -> None:
        for queue in list(self._queues):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # Make room for the end marker, then drop the watcher.
                self._queues.discard(queue)
                queue.get_nowait()
                queue.put_nowait(None)

    async def subscribe(self, snapshot: Callable[[], Payload]) -> AsyncIterator[Payload]:
        """`snapshot` is taken once the watcher is registered, so nothing published in
        between is missed."""
        queue: asyncio.Queue[Payload | None] = asyncio.Queue(SUBSCRIBER_QUEUE_SIZE)
        self._loop = asyncio.get_running_loop()
        self._queues.add(queue)
        try:
            yield snapshot()
            while True:
                item = await queue.get()
                if item is None:
                    return
                yield item
        finally:
            self._queues.discard(queue)

    def close(self) -> None:
        for queue in list(self._queues):
            queue.put_nowait(None)


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None
