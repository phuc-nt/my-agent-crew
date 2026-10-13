"""The browsers of the crew: one Chromium an agent, started at its first call, stopped when
nobody used it for a while and when the server stops.

Each agent has a profile of its own under `<home>/browser/<agent_id>/`, so what one agent is
logged in to is not another's. Every browser is started behind a proxy of its own that
refuses private addresses (`proxy.py`): there is no other way out of it. How a Chromium is
started is in `launch.py`."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import Counter
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from my_agent_crew.browser.downloads import Downloads, fresh
from my_agent_crew.browser.launch import Driver, launch
from my_agent_crew.browser.network import Allow
from my_agent_crew.browser.proxy import FilteringProxy
from my_agent_crew.browser.tabs import Tab, Tabs
from my_agent_crew.config_browser import BrowserSettings, profile_dir
from my_agent_crew.tools.web import Resolver, resolve_host

log = logging.getLogger(__name__)


@dataclass
class Session:
    agent_id: str
    context: Any
    proxy: FilteringProxy
    tabs: Tabs
    used: float
    busy: int = 0
    downloads: Downloads | None = None

    async def close(self) -> None:
        try:
            await self.context.close()
        except Exception:  # noqa: BLE001 - a browser that already died is closed
            pass
        await self.proxy.stop()


class BrowserPool:
    def __init__(
        self,
        root: Path,
        settings: BrowserSettings,
        *,
        clock: Callable[[], float] = time.monotonic,
        resolver: Resolver = resolve_host,
        allow: Allow | None = None,
    ) -> None:
        self.root = root
        self.settings = settings
        self.clock = clock
        self.resolver = resolver
        self.allow = allow
        self.driver = Driver(self._lost)
        self._sessions: dict[str, asyncio.Future[Session]] = {}
        self._closing: dict[str, asyncio.Future[bool]] = {}
        # Times an agent was taken off the browser: tools made before the last start none.
        self.left: Counter[str] = Counter()
        # Set as the server stops: a turn the stop has not ended yet starts no browser.
        self.shut = False

    async def session(self, agent_id: str) -> Session:
        """The agent's browser, started now if it is not up. The place is taken before the
        first await, so two turns that ask at once wait for one browser."""
        task = self._sessions.get(agent_id)
        if task is None:
            if self.shut:
                raise RuntimeError("the server is stopping")
            start = self._launch(agent_id, self._closing.get(agent_id))
            task = self._sessions[agent_id] = asyncio.ensure_future(start)
            task.add_done_callback(lambda done: self._failed(agent_id, done))
        return await asyncio.shield(task)

    @contextlib.asynccontextmanager
    async def hold(self, session: Session) -> AsyncIterator[Session]:
        """A browser for the length of one call: it is not stopped for being idle while a
        call is using it. The caller asked for it once; asking again here would start one."""
        session.busy += 1
        try:
            yield session
        finally:
            session.busy -= 1
            session.used = self.clock()

    def running(self, agent_id: str) -> Session | None:
        task = self._sessions.get(agent_id)
        if task is None or not task.done() or task.cancelled() or task.exception():
            return None
        return task.result()

    def peek(self, agent_id: str, owner: str, label: str = "") -> Tab | None:
        """A tab as it is now, without starting anything: what the approval gate reads."""
        session = self.running(agent_id)
        return session.tabs.find(owner, label) if session else None

    async def stop(self, agent_id: str) -> bool:
        """Whether this call stopped it; a stop someone else began is waited for all the same."""
        task = self._sessions.pop(agent_id, None)
        if task is None:
            if agent_id in self._closing:
                await asyncio.wait({self._closing[agent_id]})
            return False
        closing = self._closing[agent_id] = asyncio.ensure_future(self._close(task))
        closing.add_done_callback(
            lambda done: self._closing.get(agent_id) is done and self._closing.pop(agent_id)
        )
        return await asyncio.shield(closing)

    async def _close(self, task: asyncio.Future[Session]) -> bool:
        try:
            session = await task
        except Exception:  # noqa: BLE001 - a browser that never came up has nothing to stop
            return False
        await session.close()
        return True

    async def stop_all(self) -> None:
        for agent_id in list(self._sessions):
            await self.stop(agent_id)
        await asyncio.gather(*self._closing.values(), return_exceptions=True)
        await self.driver.stop()

    async def reap(self) -> list[str]:
        """Stop the browsers nobody used for `idle_minutes` and close the cold tabs of the
        others; the agents whose browser was stopped."""
        now, stopped = self.clock(), []
        for agent_id in list(self._sessions):
            session = self.running(agent_id)
            if session is None or session.busy:
                continue
            if now - session.used >= self.settings.idle_minutes * 60:
                stopped += [agent_id] if await self.stop(agent_id) else []
            else:
                await session.tabs.close_cold()
        return stopped

    async def _launch(self, agent_id: str, stopping: asyncio.Future[bool] | None) -> Session:
        # `stopping` is the stop that was going on when this start was asked for: a profile is
        # one browser's at a time. A stop that comes later waits for this start, not this for it.
        profile = profile_dir(self.root, agent_id)
        if stopping is not None:
            await asyncio.wait({stopping})
        driver = await self.driver.get()
        proxy = FilteringProxy(self.resolver, self.allow)
        await proxy.start()
        try:
            held = await asyncio.to_thread(fresh, profile)
            option, channel = proxy.launch_option, self.settings.channel
            context = await launch(driver, profile, channel, option, downloads=held)
        except BaseException:
            await proxy.stop()
            raise
        tabs = Tabs(context, self.settings.max_tabs, self.clock)
        session = Session(agent_id, context, proxy, tabs, self.clock())
        session.downloads = Downloads(context, held)
        context.on("close", lambda _context: self._closed(session))
        log.info("browser started for agent %s (%s)", agent_id, self.settings.channel)
        return session

    def _failed(self, agent_id: str, task: asyncio.Future[Session]) -> None:
        """A start that failed leaves no place taken: the next call tries again."""
        if (task.cancelled() or task.exception()) and self._sessions.get(agent_id) is task:
            del self._sessions[agent_id]

    def _closed(self, session: Session) -> None:
        """A browser that went away by itself (a crash, a kill) is forgotten with its proxy."""
        if self.running(session.agent_id) is session:
            del self._sessions[session.agent_id]
            closing = asyncio.ensure_future(session.proxy.stop())
            closing.add_done_callback(lambda done: done.exception())

    def _lost(self) -> None:
        """The driver went away, and no browser it started says so: all are forgotten."""
        for session in filter(None, map(self.running, list(self._sessions))):
            self._closed(session)
