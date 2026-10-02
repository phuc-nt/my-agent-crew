"""Whoever watches `/api/activity/stream`: one bounded queue per watcher, fed every payload
the hub publishes. A watcher that falls behind is cut off instead of holding the crew's
events in memory, and reconnects to a fresh snapshot."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

# A watcher that falls this many payloads behind is cut off; its stream ends and the
# browser reconnects to a fresh snapshot. One stalled tab must not hold every event of
# every run in memory for as long as it stays open.
SUBSCRIBER_QUEUE_SIZE = 256

Payload = dict[str, Any]


class Watchers:
    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[Payload | None]] = set()

    def broadcast(self, payload: Payload) -> None:
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
