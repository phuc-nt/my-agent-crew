"""An agent that is removed, or taken off the browser, while a turn of its is still running.
That turn holds the tools it began with: they start no browser again, and nothing of the
agent comes back into the folder its logins were kept in. Real Chromium."""

from __future__ import annotations

import asyncio

import pytest

from my_agent_crew import texts_browser as t
from my_agent_crew.agent.turn_context import reading_as
from my_agent_crew.browser import pool as pool_module
from my_agent_crew.browser.kit import Kit
from my_agent_crew.browser.proxy import FilteringProxy
from my_agent_crew.config_browser import profile_dir
from my_agent_crew.server.browser_runtime import Browsers
from my_agent_crew.tools.registry import ToolError
from tests.browser_crew import HERE
from tests.browser_tools import World, world

PAGES = {"/": "<title>Cửa hàng</title><h1>Đơn hàng</h1>"}


def holding(w: World) -> Browsers:
    """The crew's browsers as the server holds them, over the pool of the test."""
    return Browsers(w.pool.root, w.pool.settings, HERE, w.pool)


async def use(kit: Kit, conversation: str = "c1") -> str:
    """One call of a tool made from that kit, as a turn of the conversation makes it: the
    label of the tab it was given."""
    with reading_as(conversation):
        async with kit.tab(make=True) as (_session, tab):
            return tab.label


def held_starts(monkeypatch) -> tuple[list[FilteringProxy], asyncio.Event]:
    """Browsers whose start waits until `go` is set, and the starts that began."""
    started, go = [], asyncio.Event()

    class Held(FilteringProxy):
        async def start(self) -> None:
            started.append(self)
            await go.wait()
            await super().start()

    monkeypatch.setattr(pool_module, "FilteringProxy", Held)
    return started, go


async def refused(kit: Kit, seconds: float = 30.0) -> str:
    with pytest.raises(ToolError) as refusal:
        await asyncio.wait_for(use(kit), seconds)
    return str(refusal.value)


async def test_tools_made_before_their_agent_was_removed_start_no_browser_for_it_again(tmp_path):
    async with world(tmp_path, PAGES) as w:
        browsers, old, other = holding(w), w.kit("coach"), w.kit("ledger")
        profile = profile_dir(w.pool.root, "coach")
        assert await use(old) == "t1" and profile.is_dir()

        await browsers.forget("coach")

        assert await refused(old) == t.BROWSER_GONE
        assert w.pool.running("coach") is None and not profile.exists()
        # An agent given the id afterwards has tools of its own and a browser of its own. The
        # turn that outlived the first one still has neither, and nobody else's tools were told.
        fresh = w.kit("coach")
        assert await use(fresh) == "t1" and w.pool.running("coach") is not None
        assert await refused(old) == t.BROWSER_GONE
        assert await use(other) == "t1"


async def test_an_agent_taken_off_the_browser_keeps_its_logins_and_its_running_turn_starts_none(
    tmp_path,
):
    async with world(tmp_path, PAGES) as w:
        browsers, kit = holding(w), w.kit("coach")
        profile = profile_dir(w.pool.root, "coach")
        assert await use(kit) == "t1"
        # A stop a person asked for is not that: the next call of the same turn starts it.
        first = w.pool.running("coach")
        assert await browsers.stop("coach") is True
        assert await use(kit) == "t1" and w.pool.running("coach") is not first

        assert await browsers.retire("coach") is True

        assert await refused(kit) == t.BROWSER_GONE
        assert w.pool.running("coach") is None and profile.is_dir()
        assert await browsers.retire("coach") is False
        assert await Browsers(w.pool.root, w.pool.settings, HERE).retire("coach") is False


async def test_a_call_that_was_starting_the_browser_when_its_agent_was_removed_leaves_nothing(
    tmp_path, monkeypatch
):
    started, go = held_starts(monkeypatch)
    async with world(tmp_path, PAGES) as w:
        browsers, kit = holding(w), w.kit("coach")
        profile = profile_dir(w.pool.root, "coach")
        call = asyncio.ensure_future(use(kit))
        try:
            async with asyncio.timeout(30):
                while not started:
                    await asyncio.sleep(0.01)
            removing = asyncio.ensure_future(browsers.forget("coach"))
            await asyncio.sleep(0.1)
            waited = removing.done()
        finally:
            go.set()
        async with asyncio.timeout(30):
            await removing
            with pytest.raises(ToolError) as refusal:
                await call

        # The removal waited for the one browser that was on its way and closed it. The call
        # that had asked for it was handed that one: asking again would have started another
        # on the profile, after the folder went. It is told why at once, not left to open a
        # tab in a browser that is closing until its time is up.
        assert waited is False and len(started) == 1
        assert str(refusal.value) == t.BROWSER_GONE
        assert w.pool.running("coach") is None and not profile.exists()


async def test_a_call_whose_browser_a_person_stopped_as_it_came_up_is_told_so_at_once(
    tmp_path, monkeypatch
):
    started, go = held_starts(monkeypatch)
    async with world(tmp_path, PAGES) as w:
        browsers, kit = holding(w), w.kit("coach")
        call = asyncio.ensure_future(use(kit))
        try:
            async with asyncio.timeout(30):
                while not started:
                    await asyncio.sleep(0.01)
            stopping = asyncio.ensure_future(browsers.stop("coach"))
            await asyncio.sleep(0.1)
        finally:
            go.set()
        async with asyncio.timeout(30):
            assert await stopping is True
            with pytest.raises(ToolError) as refusal:
                await call

        assert str(refusal.value) == t.BROWSER_STOPPED
        assert w.pool.running("coach") is None and len(started) == 1
        # A stop is not a removal: the next call of the same turn starts the browser again.
        assert await use(kit) == "t1" and len(started) == 2


async def test_a_call_made_while_the_browser_of_a_removed_agent_is_still_closing_is_refused(
    tmp_path,
):
    async with world(tmp_path, PAGES) as w:
        browsers, kit = holding(w), w.kit("coach")
        profile = profile_dir(w.pool.root, "coach")
        await use(kit)
        session = w.pool.running("coach")
        gone, close = asyncio.Event(), session.close

        async def slowly() -> None:
            await gone.wait()
            await close()

        session.close = slowly
        removing = asyncio.ensure_future(browsers.forget("coach"))
        try:
            await asyncio.sleep(0.1)
            assert not removing.done()
            # Told before the stop took its first step: a call let through here would wait
            # for the closing to end and then start the browser the removal had just stopped.
            said = await refused(kit, 3)
        finally:
            gone.set()
        async with asyncio.timeout(30):
            await removing

        assert said == t.BROWSER_GONE
        assert w.pool.running("coach") is None and not profile.exists()
