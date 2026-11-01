"""Watches the activity stream while the server runs and pushes what `notices.py` picks.

A run's end can be told more than once (a job's run ends with its events, then again with
the summary its runner writes), so each request and each run is pushed once at most. A
watcher cut off for falling behind watches again, as the Telegram chat's does."""

from __future__ import annotations

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from my_agent_crew.activity.hub import ActivityHub
from my_agent_crew.store.db import Store
from my_agent_crew.webpush.notices import Notice, notice_for
from my_agent_crew.webpush.sender import send_all
from my_agent_crew.webpush.store import PushStore

logger = logging.getLogger(__name__)
REWATCH_SECONDS = 1.0
# Enough to outlast the second telling of any run's end.
REMEMBERED = 500

Send = Callable[[Notice], Awaitable[int]]


def _key(payload: dict[str, Any]) -> str:
    if payload.get("type") == "event":
        event = payload.get("event") or {}
        return "request:" + str(event.get("approval_id") or payload.get("run_id"))
    return "run:" + str((payload.get("run") or {}).get("id"))


class Notifier:
    def __init__(self, hub: ActivityHub, store: Store, push: PushStore, send: Send):
        self._hub = hub
        self._store = store
        self._push = push
        self._send = send
        self._told: OrderedDict[str, None] = OrderedDict()
        self._tasks: set[asyncio.Task[Any]] = set()

    def consider(self, payload: dict[str, Any]) -> Notice | None:
        """The notice to push for this message, unless it was pushed already or nobody
        has subscribed."""
        notice = notice_for(payload, self._store)
        if notice is None or not self._push.subscriptions():
            return None
        key = _key(payload)
        if key in self._told:
            return None
        self._told[key] = None
        while len(self._told) > REMEMBERED:
            self._told.popitem(last=False)
        return notice

    async def _push_one(self, notice: Notice) -> None:
        try:
            await self._send(notice)
        except Exception:  # one failed push must not stop the watch
            logger.exception("webpush: push failed")

    async def run(self) -> None:
        while True:
            async for payload in self._hub.subscribe():
                notice = self.consider(payload)
                if notice is not None:
                    task = asyncio.create_task(self._push_one(notice))
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)
            await asyncio.sleep(REWATCH_SECONDS)


def start_notifier(
    hub: ActivityHub, store: Store, push: PushStore, client: httpx.AsyncClient
) -> asyncio.Task[None]:
    """The watch, as a task the caller cancels when the server stops."""
    notifier = Notifier(hub, store, push, lambda notice: send_all(client, push, notice))
    return asyncio.create_task(notifier.run())
