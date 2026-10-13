"""The browsers of the crew: one Chromium an agent, started at its first call, stopped when
nobody used it for a while and when the server stops.

Each agent has a profile of its own under `<home>/browser/<agent_id>/`, so what one agent is
logged in to is not another's. Every browser is started behind a proxy of its own that
refuses private addresses (`proxy.py`): there is no other way out of it."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from my_agent_crew.browser.network import Allow
from my_agent_crew.browser.proxy import FilteringProxy
from my_agent_crew.browser.tabs import Tab, Tabs
from my_agent_crew.config_browser import BrowserSettings
from my_agent_crew.tools.web import Resolver, resolve_host

log = logging.getLogger(__name__)
VIEWPORT = {"width": 1280, "height": 800}
ACTION_MS, NAVIGATION_MS = 8_000, 20_000
# Nothing leaves the browser beside the proxy: no direct connection for loopback, no UDP that
# a proxy cannot carry.
ARGS = (
    "--proxy-bypass-list=<-loopback>",
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--disable-quic",
)


@dataclass
class Session:
    agent_id: str
    context: Any
    proxy: FilteringProxy
    tabs: Tabs
    used: float
    busy: int = 0

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
        self._clock = clock
        self.resolver = resolver
        self.allow = allow
        self._driver: asyncio.Future[Any] | None = None
        self._sessions: dict[str, asyncio.Future[Session]] = {}
        self._closing: dict[str, asyncio.Future[bool]] = {}

    async def session(self, agent_id: str) -> Session:
        """The agent's browser, started now if it is not up. The place is taken before the
        first await, so two turns that ask at once wait for one browser."""
        task = self._sessions.get(agent_id)
        if task is None:
            task = self._sessions[agent_id] = asyncio.ensure_future(self._launch(agent_id))
            task.add_done_callback(lambda done: self._failed(agent_id, done))
        return await asyncio.shield(task)

    @contextlib.asynccontextmanager
    async def hold(self, agent_id: str) -> AsyncIterator[Session]:
        """The agent's browser for the length of one call: it is not stopped for being idle
        while a call is using it."""
        session = await self.session(agent_id)
        session.busy += 1
        try:
            yield session
        finally:
            session.busy -= 1
            session.used = self._clock()

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
        task = self._sessions.pop(agent_id, None)
        if task is None:
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
        driver, self._driver = self._driver, None
        if driver is not None:
            with contextlib.suppress(Exception):
                await (await driver).stop()

    async def reap(self) -> list[str]:
        """Stop the browsers nobody used for `idle_minutes` and close the cold tabs of the
        others; the agents whose browser was stopped."""
        now, stopped = self._clock(), []
        for agent_id in list(self._sessions):
            session = self.running(agent_id)
            if session is None or session.busy:
                continue
            if now - session.used >= self.settings.idle_minutes * 60:
                stopped += [agent_id] if await self.stop(agent_id) else []
            else:
                await session.tabs.close_cold()
        return stopped

    async def _launch(self, agent_id: str) -> Session:
        if Path(agent_id).name != agent_id or agent_id in ("", ".", ".."):
            raise ValueError(f"not an agent id: {agent_id!r}")
        if agent_id in self._closing:  # a profile is one browser's at a time
            await asyncio.wait({self._closing[agent_id]})
        if self._driver is None:
            from playwright.async_api import async_playwright  # absent where no agent browses

            self._driver = asyncio.ensure_future(async_playwright().start())
        driver = await asyncio.shield(self._driver)
        proxy = FilteringProxy(self.resolver, self.allow)
        await proxy.start()
        try:
            profile = self.root / agent_id
            profile.mkdir(mode=0o700, parents=True, exist_ok=True)
            context = await driver.chromium.launch_persistent_context(
                str(profile),
                headless=True,
                channel=self.settings.channel,
                proxy=proxy.launch_option,
                accept_downloads=False,
                viewport=VIEWPORT,
                args=list(ARGS),
            )
        except BaseException:
            await proxy.stop()
            raise
        context.set_default_timeout(ACTION_MS)
        context.set_default_navigation_timeout(NAVIGATION_MS)
        tabs = Tabs(context, self.settings.max_tabs, self._clock)
        session = Session(agent_id, context, proxy, tabs, self._clock())
        context.on("close", lambda _context: self._closed(session))
        log.info("browser started for agent %s (%s)", agent_id, self.settings.channel)
        return session

    def _failed(self, agent_id: str, task: asyncio.Future[Session]) -> None:
        """A start that failed leaves no place taken: the next call tries again."""
        if (task.cancelled() or task.exception()) and self._sessions.get(agent_id) is task:
            del self._sessions[agent_id]

    def _closed(self, session: Session) -> None:
        """A browser that went away by itself (a crash, a kill) is forgotten with its proxy."""
        task = self._sessions.get(session.agent_id)
        if task is not None and task.done() and not task.cancelled() and not task.exception():
            if task.result() is session:
                del self._sessions[session.agent_id]
                closing = asyncio.ensure_future(session.proxy.stop())
                closing.add_done_callback(lambda done: done.exception())
