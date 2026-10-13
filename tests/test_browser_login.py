"""The window a person signs in through: that it is on the agent's own profile and behind a
proxy of its own, that the agent has no browser while it is open, when none is opened, and
every way it closes. Real Chromium, one nobody sees in place of the one a person would."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from my_agent_crew import texts_browser as t
from my_agent_crew.browser import login as login_module
from my_agent_crew.browser.console import LOCKED, NONE, OPEN, read_console
from my_agent_crew.browser.launch import launch
from my_agent_crew.browser.login import (
    BUSY,
    HEADED,
    LOOK_SECONDS,
    NO_CONSOLE,
    OPEN_SECONDS,
    SCREEN_LOCKED,
    LoginWindows,
    Refused,
)
from my_agent_crew.browser.logins import recalled
from my_agent_crew.browser.navigate import build_navigate
from my_agent_crew.browser.pool import BrowserPool, Reserved
from my_agent_crew.browser.proxy import FilteringProxy
from my_agent_crew.config_browser import BrowserSettings, profile_dir
from my_agent_crew.texts_browser_login import LOGIN_OPEN
from my_agent_crew.tools.registry import ToolError
from tests.browser_crew import Screen
from tests.browser_servers import Site, browsers, sites
from tests.browser_tools import talking, world

SIGNED_IN = "phien=bi-mat-123; Max-Age=3600; HttpOnly; SameSite=Lax; Path=/"
PAGES = {
    "/": "<title>Cửa hàng</title><h1>Cửa hàng</h1>",
    "/don": "<title>Đơn của tôi</title><p>Đơn số 7</p>",
    # How a site keeps a person signed in: a cookie no script reads, that outlasts the browser.
    "/vao": lambda site: (
        200,
        {"set-cookie": SIGNED_IN, "cache-control": "no-store"},
        "<title>Đã vào</title>ok",
    ),
    # What a browser is shown by whether it is signed in.
    "/toi": lambda site: (
        200,
        {"cache-control": "no-store"},
        "<title>Tôi</title><p>{}</p>".format(
            "khách quen" if "phien=bi-mat-123" in site.heads[-1].get("cookie", "") else "khách lạ"
        ),
    ),
}
AT = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


class Opener:
    """A Chromium nobody sees in place of the window, kept count of; its first `fail` starts
    do not come up."""

    def __init__(self, fail: int = 0) -> None:
        self.asked: list[str] = []
        self.fail = fail

    async def __call__(self, driver: Any, profile: Path, channel: str, proxy: Any) -> Any:
        self.asked.append(Path(profile).name)
        if self.fail:
            self.fail -= 1
            raise RuntimeError("no screen to show it on")
        return await launch(driver, profile, channel, proxy)


@dataclass
class Desk:
    pool: BrowserPool
    windows: LoginWindows
    screen: Screen
    opener: Opener
    site: Site  # what a browser may reach
    intranet: Site  # a private service: the real rule refuses it

    def profile(self, agent_id: str = "coach") -> Path:
        return profile_dir(self.pool.root, agent_id)


@asynccontextmanager
async def desk(root: Path, fail: int = 0, **own: Any) -> AsyncIterator[Desk]:
    """A crew's browsers and the windows on them, at a screen the test says the state of."""
    with sites(PAGES, {"/": "<title>Nội bộ</title>bí mật"}) as (site, intranet):
        async with browsers(root / "browser", site) as pool:
            screen, opener = Screen(), Opener(fail)
            windows = LoginWindows(pool, console=screen, opener=opener, **own)
            try:
                yield Desk(pool, windows, screen, opener, site, intranet)
            finally:
                await shut(windows)


async def shut(windows: LoginWindows) -> None:
    """A test's last step. Windows that never close are a failed test, not a run that never
    ends."""
    async with asyncio.timeout(30):
        await windows.close_all()


async def until(done: Callable[[], Any], seconds: float = 10.0) -> None:
    async with asyncio.timeout(seconds):
        while not done():
            await asyncio.sleep(0.01)


async def gone(port: int) -> bool:
    """Whether nothing answers on a port any more."""
    try:
        _reader, writer = await asyncio.open_connection("127.0.0.1", port)
    except OSError:
        return True
    writer.close()
    return False


def test_left_to_itself_a_window_is_one_a_person_sees_on_this_machines_own_screen(tmp_path):
    windows = LoginWindows(BrowserPool(tmp_path, BrowserSettings(enabled=True)))

    assert windows.opener is HEADED and windows.console is read_console
    assert (HEADED.func, HEADED.args, HEADED.keywords) == (launch, (), {"headed": True})
    # Long enough to sign in with a second step, short enough that one forgotten is no harm.
    assert windows.seconds == OPEN_SECONDS == 15 * 60 and LOOK_SECONDS == 5.0
    assert windows.now().tzinfo is UTC and abs(windows.now().timestamp() - time.time()) < 5
    assert (NO_CONSOLE, SCREEN_LOCKED, BUSY) == ("no_console", "locked", "busy")


async def test_a_window_is_on_the_agents_own_profile_and_the_agent_has_no_browser_meanwhile(
    tmp_path,
):
    async with desk(tmp_path, now=lambda: AT, seconds=600) as d:
        window = await d.windows.open("coach")

        assert d.windows.window("coach") is window and d.opener.asked == ["coach"]
        assert window.agent_id == "coach" and window.until == AT + timedelta(seconds=600)
        assert window.timer is not None and not window.timer.done()
        assert len(window.context.pages) == 1 and d.profile().is_dir()
        assert d.windows.window("reader") is None
        # A profile is one browser's at a time: no call of the agent starts another on it.
        assert d.pool.reserved == {"coach"} and d.pool.running("coach") is None
        with pytest.raises(Reserved):
            await d.pool.session("coach")
        assert d.pool.running("coach") is None
        # Another agent's browser is its own.
        other = await d.pool.session("reader")
        assert other.context.pages and d.pool.reserved == {"coach"}
        port = window.proxy.port
        assert not await gone(port)

        assert await d.windows.done("coach") is True

        assert d.windows.window("coach") is None and d.pool.reserved == set()
        assert window.context.pages == [] and await gone(port)
        # Nothing of it is left counting down to a close that already happened.
        assert window.timer.cancelled()
        assert await d.windows.done("coach") is False
        assert d.pool.running("reader") is other
        # And the agent's next call starts its own browser on the profile again.
        assert (await d.pool.session("coach")).context.pages


async def test_the_agents_idle_browser_is_stopped_first_and_what_is_signed_in_to_stays(tmp_path):
    async with desk(tmp_path) as d:
        session = await d.pool.session("coach")
        tab = await session.tabs.open("c1")
        await tab.page.goto(d.site.url("/vao"))
        assert recalled(d.profile()) is None

        window = await d.windows.open("coach")

        assert d.pool.running("coach") is None and session.context.pages == []
        assert recalled(d.profile()).keys() == {"127.0.0.1"}
        # The window is on the profile the agent's browser was: it is signed in where that was.
        assert [cookie["name"] for cookie in await window.context.cookies()] == ["phien"]
        await window.context.pages[0].goto(d.site.url("/vao", host="localhost"))

        assert await d.windows.done("coach") is True

        # What the person signed in to is written as the window closes, and is the agent's.
        assert recalled(d.profile()).keys() == {"127.0.0.1", "localhost"}
        assert "bi-mat-123" not in (d.profile() / "crew-logins.json").read_text()
        again = await d.pool.session("coach")
        assert again is not session
        held = {cookie["domain"]: cookie["name"] for cookie in await again.context.cookies()}
        assert held == {"127.0.0.1": "phien", "localhost": "phien"}


async def test_no_window_opens_under_a_call_or_while_a_browser_is_starting_for_one(tmp_path):
    async with desk(tmp_path) as d:
        starting = asyncio.ensure_future(d.pool.session("coach"))
        await asyncio.sleep(0)

        assert d.windows.why_not("coach") == BUSY
        with pytest.raises(Refused) as refused:
            await d.windows.open("coach")
        assert refused.value.why == BUSY
        session = await starting
        # A browser that is up and that no call is using is in nobody's way.
        assert d.windows.why_not("coach") == ""

        async with d.pool.hold(session):
            assert d.windows.why_not("coach") == BUSY
            assert d.windows.why_not("reader") == ""
            with pytest.raises(Refused) as refused:
                await d.windows.open("coach")
            assert refused.value.why == BUSY
            # A screen nobody could see it on is said first: waiting for the call mends nothing.
            d.screen.state = LOCKED
            assert d.windows.why_not("coach") == SCREEN_LOCKED
            d.screen.state = OPEN

        assert d.opener.asked == [] and d.pool.reserved == set()
        assert d.windows.window("coach") is None
        assert d.pool.running("coach") is session and session.context.pages
        assert d.windows.why_not("coach") == ""


@pytest.mark.parametrize(("state", "why"), [(LOCKED, SCREEN_LOCKED), (NONE, NO_CONSOLE)])
async def test_no_window_is_tried_where_nobody_could_see_it(tmp_path, state: str, why: str):
    async with desk(tmp_path) as d:
        session = await d.pool.session("coach")
        d.screen.state = state

        assert d.windows.why_not("coach") == why
        with pytest.raises(Refused) as refused:
            await d.windows.open("coach")

        assert refused.value.why == why and str(refused.value) == why
        assert d.opener.asked == [] and d.pool.reserved == set()
        # The agent's browser is stopped for a window that opens, and for no other.
        assert d.pool.running("coach") is session and session.context.pages

        d.screen.state = OPEN

        assert d.windows.why_not("coach") == ""
        assert (await d.windows.open("coach")).context.pages and d.opener.asked == ["coach"]


async def test_two_asks_at_once_open_one_window_and_a_later_ask_is_given_it_as_it_is(tmp_path):
    clock = [AT]
    async with desk(tmp_path, now=lambda: clock[0], seconds=600) as d:
        first, second = await asyncio.gather(d.windows.open("coach"), d.windows.open("coach"))

        assert first is second and d.opener.asked == ["coach"]

        clock[0] = AT + timedelta(minutes=5)
        again = await d.windows.open("coach", d.site.url("/don"))
        await asyncio.sleep(0.5)

        # Asking again neither keeps it open longer nor sends it anywhere: it is the person's.
        assert again is first and d.opener.asked == ["coach"]
        assert again.until == AT + timedelta(seconds=600)
        assert d.site.seen == [] and again.context.pages[0].url == "about:blank"


async def test_a_window_nobody_closes_is_closed_after_a_while(tmp_path):
    async with desk(tmp_path, seconds=0.3) as d:
        window = await d.windows.open("coach")
        port = window.proxy.port
        assert d.pool.reserved == {"coach"}

        await until(lambda: "coach" not in d.pool.reserved)

        assert d.windows.window("coach") is None
        assert window.context.pages == [] and await gone(port)
        assert await d.windows.done("coach") is False
        assert (await d.pool.session("coach")).context.pages


async def test_a_window_whose_last_page_the_person_closes_is_closed_for_the_crew_too(tmp_path):
    async with desk(tmp_path) as d:
        window = await d.windows.open("coach")
        first, port = window.context.pages[0], window.proxy.port
        await first.goto(d.site.url("/vao"))
        second = await window.context.new_page()

        await first.close()
        await asyncio.sleep(0.3)

        # A page the person opened beside the first keeps it open.
        assert d.windows.window("coach") is window and d.pool.reserved == {"coach"}

        await second.close()
        await until(lambda: "coach" not in d.pool.reserved)

        # A browser with no window left would still hold the profile: it is closed, what it
        # held is written, and the agent's own browser starts on the profile again.
        assert d.windows.window("coach") is None and await gone(port)
        assert window.timer.cancelled()
        assert recalled(d.profile()).keys() == {"127.0.0.1"}
        assert (await d.pool.session("coach")).context.pages


async def test_a_browser_the_person_quits_ends_the_window_and_what_it_held_is_written(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(login_module, "LOOK_SECONDS", 0.05)
    async with desk(tmp_path) as d:
        window = await d.windows.open("coach")
        port = window.proxy.port
        assert window.held is None
        await window.context.pages[0].goto(d.site.url("/vao"))
        # It is asked while it is up: one that was quit can no longer be.
        await until(lambda: bool(window.held))
        assert window.held.keys() == {"127.0.0.1"} and recalled(d.profile()) is None

        await window.context.close()
        await until(lambda: "coach" not in d.pool.reserved)

        assert d.windows.window("coach") is None and await gone(port)
        assert recalled(d.profile()).keys() == {"127.0.0.1"}
        assert await d.windows.done("coach") is False
        again = await d.pool.session("coach")
        assert [cookie["name"] for cookie in await again.context.cookies()] == ["phien"]


class Leaf:
    def on(self, _event: str, _heard: Any) -> None:
        pass


class Quit:
    """A window's browser as the crew is left with it: it says what it holds while it is up,
    nothing once it stops answering, and tells whoever listens when the person quits it."""

    def __init__(self, cookies: list[dict[str, Any]]) -> None:
        self.jar: list[dict[str, Any]] | None = cookies
        self.pages: list[Leaf] = [Leaf()]
        self.heard: dict[str, Any] = {}
        self.asked = 0

    def on(self, event: str, heard: Any) -> None:
        self.heard[event] = heard

    async def cookies(self) -> list[dict[str, Any]]:
        self.asked += 1
        if self.jar is None:
            raise RuntimeError("Target page, context or browser has been closed")
        return self.jar

    async def close(self) -> None:
        raise RuntimeError("Target page, context or browser has been closed")

    def quit(self) -> None:
        self.jar, self.pages = None, []
        self.heard["close"](self)


async def test_of_a_browser_that_stopped_answering_what_it_was_last_seen_to_hold_is_written(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(login_module, "LOOK_SECONDS", 0.02)
    soon = time.time() + 3_600
    signed_in = {"name": "sid", "value": "bi-mat-123", "domain": ".Shop.Example", "expires": soon}
    browser = Quit([{**signed_in, "httpOnly": True, "sameSite": "Lax"}])

    async def opener(driver: Any, profile: Path, channel: str, proxy: Any) -> Quit:
        profile.mkdir(parents=True)
        return browser

    async with browsers(tmp_path / "browser") as pool:
        windows = LoginWindows(pool, console=Screen(), opener=opener)
        try:
            window = await windows.open("coach")
            port = window.proxy.port
            await until(lambda: window.held is not None)
            assert window.held == {"shop.example": soon}

            # A look that is told nothing keeps what the one before it saw.
            browser.jar, asked = None, browser.asked
            await until(lambda: browser.asked >= asked + 3)
            assert window.held == {"shop.example": soon}
            assert recalled(profile_dir(pool.root, "coach")) is None

            browser.quit()
            await until(lambda: "coach" not in pool.reserved)

            assert recalled(profile_dir(pool.root, "coach")) == {"shop.example": soon}
            assert windows.window("coach") is None and await gone(port)
            written = (profile_dir(pool.root, "coach") / "crew-logins.json").read_text()
            assert "bi-mat-123" not in written and "sid" not in written
        finally:
            await shut(windows)


async def test_a_window_that_would_not_open_leaves_the_agent_its_browser(tmp_path, monkeypatch):
    stopped: list[int] = []

    class Watched(FilteringProxy):
        async def stop(self) -> None:
            stopped.append(self.port)
            await super().stop()

    monkeypatch.setattr(login_module, "FilteringProxy", Watched)
    async with desk(tmp_path, fail=1) as d:
        with pytest.raises(RuntimeError, match="no screen to show it on"):
            await d.windows.open("coach")

        assert d.windows.window("coach") is None and d.pool.reserved == set()
        # The proxy started for it is not left answering.
        assert len(stopped) == 1 and await gone(stopped[0])
        session = await d.pool.session("coach")
        assert session.context.pages and d.windows.why_not("coach") == ""

        window = await d.windows.open("coach")

        assert window.context.pages and d.opener.asked == ["coach", "coach"]
        assert d.pool.running("coach") is None and len(stopped) == 1


async def test_a_request_that_gives_up_waiting_still_leaves_a_window_the_crew_knows_of(tmp_path):
    async with desk(tmp_path) as d:
        asking = asyncio.ensure_future(d.windows.open("coach"))
        await asyncio.sleep(0)

        asking.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asking

        # Half opened it would hold the profile with nobody knowing to close it.
        await until(lambda: d.windows.window("coach") is not None)
        assert d.pool.reserved == {"coach"} and d.opener.asked == ["coach"]
        assert await d.windows.done("coach") is True
        assert d.pool.reserved == set()


async def test_the_address_a_window_starts_on_is_checked_as_a_call_of_the_agent_is(tmp_path):
    async with desk(tmp_path) as d:
        with pytest.raises(ToolError) as no_page:
            await d.windows.open("coach", "file:///etc/hosts")
        with pytest.raises(ToolError) as private:
            await d.windows.open("coach", d.intranet.url("/"))
        with pytest.raises(ToolError) as nowhere:
            await d.windows.open("coach", "https://shop.example/dang-nhap")

        assert str(no_page.value) == t.URL_SCHEME
        assert str(private.value) == t.URL_PRIVATE.format(host="127.0.0.1")
        assert str(nowhere.value).startswith(
            t.URL_UNREACHABLE.split("{error}")[0].format(host="shop.example")
        )
        # Refused before anything is touched: no window, and the agent keeps its browser.
        assert d.opener.asked == [] and d.pool.reserved == set()
        assert d.windows.window("coach") is None

        window = await d.windows.open("coach", d.site.url("/don"))

        await until(lambda: "GET /don" in d.site.seen)
        await until(lambda: window.context.pages[0].url == d.site.url("/don"))
        assert d.intranet.seen == []


async def test_a_window_is_the_persons_before_the_address_it_starts_on_has_answered(tmp_path):
    answer, answered = threading.Event(), []

    def slow(_site: Site) -> tuple[int, dict[str, str], str]:
        answer.wait(8)
        answered.append("GET /cho")
        return 200, {}, "<title>Chậm</title>ok"

    async with desk(tmp_path) as d:
        d.site.pages["/cho"] = slow
        try:
            window = await d.windows.open("coach", d.site.url("/cho"))

            # A site that is slow to answer keeps nobody waiting for the window.
            assert answered == [] and d.windows.window("coach") is window
            await until(lambda: "GET /cho" in d.site.seen)
            assert answered == []
        finally:
            answer.set()
        await until(lambda: window.context.pages[0].url == d.site.url("/cho"))
        assert answered == ["GET /cho"]


async def test_a_close_meant_for_a_window_that_is_gone_leaves_the_one_open_now(tmp_path):
    async with desk(tmp_path) as d:
        old = await d.windows.open("coach")
        assert await d.windows.done("coach") is True
        new = await d.windows.open("coach")
        assert new is not old and d.opener.asked == ["coach", "coach"]

        # What an earlier window set going (its time running out, its last page closing) may
        # arrive after the next one opened.
        assert await d.windows.done("coach", old) is False

        assert d.windows.window("coach") is new and new.context.pages
        assert d.pool.reserved == {"coach"} and not await gone(new.proxy.port)
        assert not new.timer.done()
        assert await d.windows.done("coach", new) is True
        assert d.windows.window("coach") is None and d.pool.reserved == set()


async def test_a_window_reaches_nothing_the_agents_own_browser_would_not(tmp_path):
    async with desk(tmp_path) as d:
        window = await d.windows.open("coach")
        page = window.context.pages[0]

        refused = await page.goto(d.intranet.url("/"))

        # A person at the window is sent where a page says as easily as the agent is.
        assert refused.status == 403 and d.intranet.seen == []
        assert window.proxy.refused_since(0) == ["127.0.0.1"]
        assert (await page.goto(d.site.url("/"))).status == 200
        assert await page.title() == "Cửa hàng"


async def test_every_window_is_closed_at_once_one_that_is_still_opening_included(tmp_path):
    async with desk(tmp_path) as d:
        opened = await d.windows.open("coach")
        opening = asyncio.ensure_future(d.windows.open("reader"))
        await asyncio.sleep(0)
        assert d.windows.window("reader") is None

        await d.windows.close_all()

        late = await opening
        assert d.opener.asked == ["coach", "reader"]
        assert d.windows.window("coach") is None and d.windows.window("reader") is None
        assert d.pool.reserved == set()
        assert opened.context.pages == [] and late.context.pages == []
        assert await gone(opened.proxy.port) and await gone(late.proxy.port)
        # Nothing is left on either profile: the agents' own browsers start on them.
        for agent_id in ("coach", "reader"):
            assert (await d.pool.session(agent_id)).context.pages, agent_id


@talking("signing-in")
async def test_a_call_of_the_agent_is_told_a_person_is_signing_in_and_reads_signed_in_after(
    tmp_path,
):
    async with world(tmp_path, PAGES) as w:
        windows = LoginWindows(w.pool, console=Screen(), opener=launch)
        go = build_navigate(w.kit())
        try:
            assert "khách lạ" in await go.run({"url": w.site.url("/toi")})
            window = await windows.open("coach")
            await window.context.pages[0].goto(w.site.url("/vao"))
            asked = len(w.site.seen)

            with pytest.raises(ToolError) as told:
                await go.run({"url": w.site.url("/toi")})

            assert str(told.value) == LOGIN_OPEN
            assert w.pool.running("coach") is None and len(w.site.seen) == asked
            # Another agent's call is nobody's business but its own.
            assert "khách lạ" in await build_navigate(w.kit("reader")).run(
                {"url": w.site.url("/toi")}
            )

            assert await windows.done("coach") is True

            assert "khách quen" in await go.run({"url": w.site.url("/toi")})
        finally:
            await shut(windows)
