"""The window a person signs in through: a Chromium on the agent's own profile, shown on the
screen for a while, so the person signs in where the agent will later read.

A profile is one browser's at a time. The agent's own browser is stopped before the window
opens, the agent has none while it is open (`pool.reserved`), and no window opens under a
call that asked for the browser. The window goes out through a proxy of its own that refuses
private addresses, as the agent's browser does. It closes when the person says they are done,
when they close it themselves, when the driver it was started through goes away, and by
itself after a while: one left open would keep the agent off its browser for good. None is
opened once the server is going down, nor for an agent that left while it was asked for."""

from __future__ import annotations

import asyncio
import functools
import logging
from collections import defaultdict
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

from my_agent_crew.browser.console import LOCKED, NONE, read_console
from my_agent_crew.browser.launch import launch, shut_down
from my_agent_crew.browser.login_window import Window
from my_agent_crew.browser.network import check_url
from my_agent_crew.browser.pool import BrowserPool
from my_agent_crew.browser.proxy import FilteringProxy
from my_agent_crew.config_browser import profile_dir

log = logging.getLogger(__name__)

# Why no window is opened now, as the web is told.
NO_CONSOLE, SCREEN_LOCKED, BUSY, STOPPING = "no_console", "locked", "busy", "stopping"
# The agent was removed, or taken off the browser, while its window was asked for.
GONE = "gone"
OPEN_SECONDS = 15 * 60
# How often an open window is asked what it holds.
LOOK_SECONDS = 5.0
# A Chromium a person can see. Tests put one nobody sees in its place.
HEADED = functools.partial(launch, headed=True)


class Refused(Exception):
    def __init__(self, why: str) -> None:
        super().__init__(why)
        self.why = why


class LoginWindows:
    def __init__(
        self,
        pool: BrowserPool,
        *,
        console: Callable[[], str] = read_console,
        opener: Callable[..., Any] = HEADED,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        seconds: float = OPEN_SECONDS,
    ) -> None:
        self.pool = pool
        self.console = console
        self.opener = opener
        self.now = now
        self.seconds = seconds
        self._windows: dict[str, Window] = {}
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._tasks: set[asyncio.Future[Any]] = set()
        pool.on_lost.append(self._lost)

    def window(self, agent_id: str) -> Window | None:
        return self._windows.get(agent_id)

    def why_not(self, agent_id: str) -> str:
        """Why no window can be opened for the agent now; nothing when one can."""
        state = self.console()
        if state in (NONE, LOCKED):
            return NO_CONSOLE if state == NONE else SCREEN_LOCKED
        return BUSY if self.pool.in_use(agent_id) else ""

    async def open(self, agent_id: str, url: str = "") -> Window:
        """The agent's window, opened now if none is. An address it is to start on is checked
        as one of the agent's own calls is, and refused in the same words (`ToolError`);
        `Refused` says why none is opened; what the browser raises means it would not open."""
        left = self.pool.left[agent_id]  # looking an address up takes a while
        address = await check_url(url, self.pool.resolver, self.pool.allow) if url else ""
        return await asyncio.shield(self._kept(self._open(agent_id, address, left)))

    async def done(self, agent_id: str, only: Window | None = None) -> bool:
        """Close the agent's window: `only` that one, where a window is named. Whether there
        was one for this call to close."""
        return await asyncio.shield(self._kept(self._done(agent_id, only)))

    async def close_all(self) -> None:
        """Close every window, one that is still opening included, and wait for whatever a
        closed window set going."""
        while self._tasks or self._windows:
            for agent_id in list(self._windows):
                await self.done(agent_id)
            await asyncio.gather(*self._tasks, return_exceptions=True)
            # Work that ended is forgotten at the loop's next turn, and waiting for work that
            # has ended takes none: without this turn the loop above would never be left.
            await asyncio.sleep(0)

    def _kept(self, work: Coroutine[Any, Any, Any]) -> asyncio.Future[Any]:
        """Work that goes on to its end whoever stops waiting for it: a window half opened or
        half closed would leave the profile with two browsers, or the agent with none."""
        task = asyncio.ensure_future(work)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(lambda done: done.cancelled() or done.exception())
        return task

    async def _open(self, agent_id: str, address: str, left: int) -> Window:
        async with self._locks[agent_id]:
            if self.pool.left[agent_id] != left:  # not the agent the window was asked for
                raise Refused(GONE)
            window = self._windows.get(agent_id)
            if window is not None:
                return window
            # A window opened under a server that is stopping would be left on the screen.
            why = STOPPING if self.pool.shut else self.why_not(agent_id)
            if why:
                raise Refused(why)
            # Taken before the first await: from here on no call starts the agent's browser.
            self.pool.reserved.add(agent_id)
            try:
                window = self._windows[agent_id] = await self._start(agent_id)
            except BaseException:
                self.pool.reserved.discard(agent_id)
                raise
        pages = window.context.pages
        if address and pages:  # not waited for: the window is the person's either way
            self._kept(pages[0].goto(address))
        return window

    async def _start(self, agent_id: str) -> Window:
        pool = self.pool
        await pool.stop(agent_id)
        driver = await pool.driver.get()
        proxy = FilteringProxy(pool.resolver, pool.allow)
        await proxy.start()
        context = None
        try:
            profile, channel = profile_dir(pool.root, agent_id), pool.settings.channel
            context = await self.opener(driver, profile, channel, proxy.launch_option)
            closes = self.now() + timedelta(seconds=self.seconds)
            window = Window(agent_id, context, proxy, closes)

            def left(_gone: Any = None) -> None:
                # The person closed the last of it, or quit the browser.
                if not context.pages:
                    self._kept(self._done(agent_id, window))

            def watch(page: Any) -> None:
                page.on("close", left)

            for page in context.pages or [await context.new_page()]:
                watch(page)
            context.on("page", watch)
            context.on("close", left)
            window.timer = asyncio.ensure_future(self._expire(window))
        except BaseException:
            # A browser that came up and is no window yet is nobody's to close but ours.
            try:
                if context is not None:
                    await shut_down(context)
            finally:
                await proxy.stop()
            raise
        log.info("login window opened for agent %s", agent_id)
        return window

    async def _expire(self, window: Window) -> None:
        loop = asyncio.get_running_loop()
        end = loop.time() + self.seconds
        while (left := end - loop.time()) > 0:
            await asyncio.sleep(min(LOOK_SECONDS, left))
            await window.look()
        log.info("login window of agent %s closed: nobody said they were done", window.agent_id)
        await self.done(window.agent_id, window)

    def _lost(self) -> None:
        """The driver went away and every window with it, without a word: each is closed for
        the crew as one that can no longer be asked anything."""
        for agent_id, window in list(self._windows.items()):
            self._kept(self._done(agent_id, window, gone=True))

    async def _done(self, agent_id: str, only: Window | None, gone: bool = False) -> bool:
        async with self._locks[agent_id]:
            window = self._windows.get(agent_id)
            if window is None or (only is not None and window is not only):
                return False
            del self._windows[agent_id]
            try:
                await window.close(profile_dir(self.pool.root, agent_id), gone=gone)
            finally:
                self.pool.reserved.discard(agent_id)
            return True
