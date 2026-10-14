"""The window a person signs in through, as the web asks for it and is told of it: what an
agent's browser card reads of it in each state, the words each refusal comes in, what closes
it besides the person, and where the browser is told to be signed in. Real Chromium, one
nobody sees in place of the window a person would be shown."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from playwright.async_api import Error as BrowserError

from my_agent_crew import texts
from my_agent_crew import texts_browser as told_to_a_model
from my_agent_crew import texts_browser_login as said
from my_agent_crew.browser.console import LOCKED, NONE, OPEN
from my_agent_crew.browser.install import NO_BROWSER, Installed
from my_agent_crew.browser.kit import NAVIGATE, SNAPSHOT, TABS
from my_agent_crew.browser.launch import Stuck
from my_agent_crew.browser.login import OPEN_SECONDS
from my_agent_crew.browser.logins import FILE, read, recalled
from my_agent_crew.config_browser import browser_root
from my_agent_crew.server import browser_runtime
from my_agent_crew.server.app import create_app
from my_agent_crew.tools.registry import ToolError
from tests.browser_crew import HERE, ON, built, crew_home
from tests.test_browser_login import gone
from tests.test_browser_routes import DOWN, NO_PROFILE, NO_WINDOW, Crew, serving, until

SECRETS = ("phien", "bi-mat-123")
# How a site keeps a person signed in: a cookie no script reads, that outlasts the browser.
SIGNS_IN = (
    200,
    {
        "set-cookie": "phien=bi-mat-123; Max-Age=3600; HttpOnly; SameSite=Lax; Path=/",
        "cache-control": "no-store",
    },
    "<title>Đã vào</title>ok",
)


@pytest_asyncio.fixture
async def crew(tmp_path: Path, monkeypatch) -> AsyncIterator[Crew]:
    agents = {"coach": "browser: act\n", "reader": "browser: read\n", "plain": "description: x\n"}
    async with serving(tmp_path, monkeypatch, **agents) as made:
        made.site.pages["/vao"] = lambda site: SIGNS_IN
        yield made


async def ask(crew: Crew, agent_id: str = "coach", **body: Any) -> httpx.Response:
    return await crew.client.post(f"/api/agents/{agent_id}/browser/login", json=body or None)


async def done(crew: Crew, agent_id: str = "coach") -> httpx.Response:
    return await crew.client.post(f"/api/agents/{agent_id}/browser/login/done")


def not_now(why: str) -> dict[str, Any]:
    return {"open": False, "until": None, "available": False, "why": why}


async def signed_in(context: Any) -> None:
    """Waits until the browser holds what the site signed it in with."""
    async with asyncio.timeout(10):
        while not await read(context):
            await asyncio.sleep(0.02)


async def test_a_window_is_opened_told_until_when_and_closed_when_the_person_says_done(
    crew: Crew,
):
    before = time.time()

    reply = await ask(crew)

    assert reply.status_code == 200, reply.text
    closes = reply.json()["until"]
    assert reply.json() == {"open": True, "until": closes}
    # A moment of the one clock every reader shares, a quarter of an hour away.
    moment = datetime.fromisoformat(closes)
    assert closes.endswith("+00:00") and moment.utcoffset() == timedelta(0)
    assert len(closes) == len("2026-10-13T08:00:00+00:00")  # told to the second
    assert before - 1 + OPEN_SECONDS <= moment.timestamp() <= time.time() + OPEN_SECONDS
    window = crew.windows.window("coach")
    # The window is the person's and no browser of the agent's: none is told as running.
    here = {"open": True, "until": closes, "available": False, "why": ""}
    assert await crew.told("coach") == {"mode": "act", **DOWN, "login": here, "logins": []}
    assert (await crew.client.get("/api/connections")).json()["browser"]["running"] == []

    # Asked again it is told as it is: it stays open no longer and goes nowhere new.
    again = await ask(crew, url=crew.site.url("/don"))
    assert (again.status_code, again.json()) == (200, {"open": True, "until": closes})
    assert crew.windows.window("coach") is window
    # A word about another agent's window is no word about this one.
    other = await done(crew, "reader")
    assert (other.status_code, other.json()) == (200, {"closed": False})
    assert (await crew.told("coach"))["login"] == here

    reply = await done(crew)

    assert (reply.status_code, reply.json()) == (200, {"closed": True})
    assert window.context.pages == [] and crew.windows.window("coach") is None
    # A browser closed on the profile, so what it held is known: nothing a person is known by.
    assert await crew.told("coach") == {"mode": "act", **DOWN, "logins": []}
    assert crew.site.seen == []
    reply = await done(crew)
    assert (reply.status_code, reply.json()) == (200, {"closed": False})
    # An agent that only reads has a profile to sign in on as well.
    assert (await ask(crew, "reader")).status_code == 200
    assert (await crew.told("reader"))["login"]["open"] is True
    assert (await crew.told("coach"))["login"] == NO_WINDOW


async def test_a_window_starts_on_the_address_it_is_asked_with_and_empty_without_one(crew: Crew):
    for nothing in (None, {}, {"url": "   "}):
        reply = await crew.client.post("/api/agents/coach/browser/login", json=nothing)
        assert reply.status_code == 200, nothing
        (page,) = crew.windows.window("coach").context.pages
        assert page.url == "about:blank", nothing
        assert (await done(crew)).json() == {"closed": True}
    assert crew.site.seen == []

    reply = await ask(crew, url=f"  {crew.site.url('/don')}\n")

    assert reply.status_code == 200, reply.text
    (page,) = crew.windows.window("coach").context.pages
    await until(lambda: page.url == crew.site.url("/don"))
    # The browser asks for the site's icon on its own, some time after the page.
    assert [asked for asked in crew.site.seen if asked != "GET /favicon.ico"] == ["GET /don"]


@pytest.mark.parametrize(
    ("state", "why", "sentence"),
    [(LOCKED, "locked", said.LOGIN_LOCKED), (NONE, "no_console", said.LOGIN_NO_CONSOLE)],
)
async def test_where_nobody_could_see_a_window_none_is_opened_and_the_reason_is_told(
    crew: Crew, state: str, why: str, sentence: str
):
    await crew.call("coach", NAVIGATE, "conv-1", url=crew.site.url("/"))
    session = crew.pool.running("coach")
    crew.screen.state = state

    told = await crew.told("coach")
    reply = await ask(crew)

    assert told["login"] == not_now(why)
    assert (reply.status_code, reply.json()) == (409, {"detail": sentence})
    # The agent's browser was not stopped for a window that never came.
    assert crew.pool.running("coach") is session and crew.pool.reserved == set()
    assert crew.windows.window("coach") is None
    closed = await done(crew)
    assert (closed.status_code, closed.json()) == (200, {"closed": False})
    # An agent with no browser is told that, whatever the screen.
    assert (await crew.told("plain"))["login"] == NO_PROFILE
    # The screen is read each time it is asked after: once a person is at it, a window opens.
    crew.screen.state = OPEN
    assert (await crew.told("coach"))["login"] == NO_WINDOW
    assert (await ask(crew)).status_code == 200


async def test_no_window_is_opened_under_a_call_of_the_agent_and_a_locked_screen_is_said_first(
    crew: Crew,
):
    await crew.call("coach", NAVIGATE, "conv-1", url=crew.site.url("/"))
    session = crew.pool.running("coach")
    slow = crew.going("coach", "conv-1")
    await until(lambda: session.busy)

    told = await crew.told("coach")
    reply = await ask(crew)

    assert told["login"] == not_now("busy")
    assert (reply.status_code, reply.json()) == (409, {"detail": said.LOGIN_BUSY})
    assert crew.pool.running("coach") is session and not slow.done()
    assert crew.windows.window("coach") is None and crew.pool.reserved == set()
    # Another agent's call is nothing in the way of this one's window.
    assert (await crew.told("reader"))["login"] == NO_WINDOW
    # Unlocking comes before waiting: a person told to wait would come back to a locked screen.
    crew.screen.state = LOCKED
    assert (await crew.told("coach"))["login"] == not_now("locked")
    assert (await ask(crew)).json() == {"detail": said.LOGIN_LOCKED}
    crew.screen.state = OPEN

    # Stopped first, as the sentence says, the browser is in the way no longer.
    stopped = await crew.client.post("/api/agents/coach/browser/stop")
    assert stopped.json() == {"stopped": True}
    with pytest.raises(ToolError):
        await asyncio.wait_for(slow, 5)
    assert (await crew.told("coach"))["login"] == NO_WINDOW
    assert (await ask(crew)).status_code == 200


@pytest.mark.parametrize("agent_id", ["plain", "default"])
async def test_an_agent_with_no_browser_has_no_profile_to_sign_in_on(crew: Crew, agent_id: str):
    reply = await ask(crew, agent_id, url=crew.site.url("/"))

    assert (reply.status_code, reply.json()) == (409, {"detail": said.LOGIN_OFF})
    closed = await done(crew, agent_id)
    assert (closed.status_code, closed.json()) == (200, {"closed": False})
    told = await crew.told(agent_id)
    assert (told["login"], told["logins"]) == (NO_PROFILE, None)
    assert crew.windows.window(agent_id) is None and crew.pool.reserved == set()
    assert not browser_root(crew.home).exists() and crew.site.seen == []


@pytest.mark.parametrize(
    ("config", "found"), [("", HERE), (ON, Installed(False, missing=NO_BROWSER))]
)
async def test_on_a_machine_with_no_browser_to_start_there_is_no_window_to_open(
    tmp_path: Path, monkeypatch, config: str, found: Installed
):
    monkeypatch.setattr(browser_runtime, "installed", lambda channel, env: found)
    rt = built(crew_home(tmp_path, config=config, coach="browser: act\n"))
    app = create_app(rt, schedule=False)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as web:
            asked = await web.post("/api/agents/coach/browser/login")
            closed = await web.post("/api/agents/coach/browser/login/done")

    assert (asked.status_code, asked.json()) == (409, {"detail": said.LOGIN_OFF})
    assert (closed.status_code, closed.json()) == (200, {"closed": False})
    assert rt.browsers.windows is None


@pytest.mark.parametrize("path", ["/browser/login", "/browser/login/done"])
async def test_a_window_of_an_agent_the_crew_does_not_have_is_a_404(crew: Crew, path: str):
    reply = await crew.client.post(f"/api/agents/ghost{path}")

    assert reply.status_code == 404
    assert reply.json() == {"detail": texts.AGENT_UNKNOWN.format(agent_id="ghost")}
    assert crew.pool.reserved == set() and not browser_root(crew.home).exists()


# What became of the agent while the address its window starts on was looked up (the values
# its `browser` key was given, None for the agent removed), and what the person is then told.
LEFT = {
    "removed": ((None,), 404, texts.AGENT_UNKNOWN.format(agent_id="coach")),
    "taken off the browser": (("off",), 409, said.LOGIN_OFF),
    "taken off and put back": (("off", "act"), 409, said.LOGIN_CHANGED),
}


@pytest.mark.parametrize("left", list(LEFT))
async def test_an_agent_that_left_while_its_address_was_looked_up_is_given_no_window(
    crew: Crew, left: str
):
    edits, status, sentence = LEFT[left]
    loop, named, replies = asyncio.get_running_loop(), crew.pool.resolver, []

    async def edited() -> None:
        for mode in edits:
            if mode is None:
                replies.append(await crew.client.delete("/api/agents/coach"))
            else:
                body = {"profile": {"browser": mode}}
                replies.append(await crew.client.patch("/api/agents/coach", json=body))

    def leaving(host: str) -> list[str]:
        # The person's request is waiting for this answer when the agent is edited.
        asyncio.run_coroutine_threadsafe(edited(), loop).result(30)
        return named(host)

    crew.pool.resolver = leaving

    reply = await ask(crew, url=crew.site.url("/don"))

    assert [r.is_success for r in replies] == [True] * len(edits)
    assert (reply.status_code, reply.json()) == (status, {"detail": sentence})
    # No browser came up on the profile of an agent that is not the one it was asked for.
    assert crew.windows.window("coach") is None and crew.pool.reserved == set()
    assert not (browser_root(crew.home) / "coach").exists() and crew.site.seen == []
    if status == 409 and sentence == said.LOGIN_CHANGED:
        # Asked again, of the agent as it is now, the window opens.
        crew.pool.resolver = named
        assert (await ask(crew, url=crew.site.url("/don"))).status_code == 200
        assert "Bấm lại" in said.LOGIN_CHANGED


async def test_no_window_is_started_on_an_address_no_browser_of_the_crew_goes_to(crew: Crew):
    await crew.call("coach", NAVIGATE, "conv-1", url=crew.site.url("/"))
    session, seen = crew.pool.running("coach"), list(crew.site.seen)
    refused = {
        "file:///etc/hosts": told_to_a_model.URL_SCHEME,
        "http://127.0.0.1:9/": told_to_a_model.URL_PRIVATE.format(host="127.0.0.1"),
    }

    for address, sentence in refused.items():
        reply = await ask(crew, url=address)
        assert (reply.status_code, reply.json()) == (422, {"detail": sentence}), address
    reply = await ask(crew, url="https://shop.example/dang-nhap")
    unknown = told_to_a_model.URL_UNREACHABLE.format(host="shop.example", error="")
    assert reply.status_code == 422 and reply.json()["detail"].startswith(unknown)

    # Nothing was stopped and nothing opened for an address that was refused.
    assert crew.pool.running("coach") is session and crew.pool.reserved == set()
    assert (await crew.told("coach"))["login"] == NO_WINDOW
    # Refused of a window that is open as well, which stays as it is.
    assert (await ask(crew)).status_code == 200
    window = crew.windows.window("coach")
    reply = await ask(crew, url="file:///etc/hosts")
    assert (reply.status_code, reply.json()) == (422, {"detail": told_to_a_model.URL_SCHEME})
    assert crew.windows.window("coach") is window and crew.site.seen == seen


async def test_a_browser_that_will_not_show_a_window_is_told_in_its_own_first_words(crew: Crew):
    await crew.call("coach", NAVIGATE, "conv-1", url=crew.site.url("/"))
    shown = crew.windows.opener

    async def will_not(*_asked: Any) -> Any:
        raise BrowserError("Missing X server or $DISPLAY\nCall log:\n  - <launching> /a/path")

    crew.windows.opener = will_not
    reply = await ask(crew)

    words = said.LOGIN_FAILED.format(error="Missing X server or $DISPLAY")
    assert (reply.status_code, reply.json()) == (409, {"detail": words})
    # The agent is left its browser: nobody holds its profile, and its next call starts one.
    assert crew.windows.window("coach") is None and crew.pool.reserved == set()
    assert (await crew.told("coach"))["login"] == NO_WINDOW
    await crew.call("coach", NAVIGATE, "conv-1", url=crew.site.url("/don"))
    assert [tab["title"] for tab in (await crew.told("coach"))["tabs"]] == ["Đơn của tôi"]

    # A start that was given up says so in its own words, as a browser's refusal does.
    async def never(*_asked: Any) -> Any:
        raise Stuck("Chromium did not start within 40 seconds")

    crew.windows.opener = never
    reply = await ask(crew)
    words = said.LOGIN_FAILED.format(error="Chromium did not start within 40 seconds")
    assert (reply.status_code, reply.json()) == (409, {"detail": words})
    assert crew.windows.window("coach") is None and crew.pool.reserved == set()

    # A fault of the crew's own is no browser's: it is not dressed as one.
    async def broken(*_asked: Any) -> Any:
        raise RuntimeError("a fault of the crew's own")

    crew.windows.opener = broken
    with pytest.raises(RuntimeError, match="a fault of the crew's own"):
        await ask(crew)
    assert crew.windows.window("coach") is None and crew.pool.reserved == set()
    # And the window opens once the browser will show one.
    crew.windows.opener = shown
    assert (await ask(crew)).status_code == 200


async def test_a_server_that_is_going_down_opens_no_window_and_says_so(crew: Crew):
    crew.pool.shut = True

    reply = await ask(crew)

    assert (reply.status_code, reply.json()) == (409, {"detail": said.LOGIN_STOPPING})
    assert crew.windows.window("coach") is None and crew.pool.reserved == set()
    assert "đang dừng" in said.LOGIN_STOPPING


async def test_stopping_the_browser_closes_the_window_a_person_has_open_on_it(crew: Crew):
    assert (await ask(crew)).status_code == 200
    window = crew.windows.window("coach")

    reply = await crew.client.post("/api/agents/coach/browser/stop")

    assert (reply.status_code, reply.json()) == (200, {"stopped": True})
    assert crew.windows.window("coach") is None and crew.pool.reserved == set()
    assert window.context.pages == [] and await gone(window.proxy.port)
    assert await crew.told("coach") == {"mode": "act", **DOWN, "logins": []}
    reply = await crew.client.post("/api/agents/coach/browser/stop")
    assert (reply.status_code, reply.json()) == (200, {"stopped": False})
    await crew.call("coach", NAVIGATE, "conv-1", url=crew.site.url("/don"))
    assert (await crew.told("coach"))["running"] is True


async def test_an_agent_taken_off_the_browser_or_out_of_the_crew_has_its_window_closed(
    crew: Crew,
):
    for agent_id in ("coach", "reader"):
        assert (await ask(crew, agent_id)).status_code == 200
    mine, theirs = (crew.windows.window(agent_id) for agent_id in ("coach", "reader"))

    # Fewer rights leave the agent a browser, and the person the window on its profile.
    reply = await crew.client.patch("/api/agents/coach", json={"profile": {"browser": "read"}})
    assert reply.status_code == 200, reply.text
    assert crew.windows.window("coach") is mine and len(mine.context.pages) == 1

    reply = await crew.client.patch("/api/agents/coach", json={"profile": {"browser": "off"}})

    assert reply.status_code == 200, reply.text
    assert crew.windows.window("coach") is None and "coach" not in crew.pool.reserved
    assert mine.context.pages == [] and await gone(mine.proxy.port)
    assert await crew.told("coach") == {"mode": "off", **DOWN, "login": NO_PROFILE}
    # What was signed in to waits for the day the agent is given the browser back.
    assert (browser_root(crew.home) / "coach").is_dir()
    assert crew.windows.window("reader") is theirs

    reply = await crew.client.delete("/api/agents/reader")

    assert reply.status_code in (200, 204), reply.text
    assert crew.windows.window("reader") is None and crew.pool.reserved == set()
    assert theirs.context.pages == [] and await gone(theirs.proxy.port)
    assert sorted(path.name for path in browser_root(crew.home).iterdir()) == ["coach"]


async def test_a_server_that_goes_down_closes_a_window_while_it_can_still_say_what_it_holds(
    tmp_path: Path, monkeypatch
):
    async with serving(tmp_path, monkeypatch, coach="browser: act\n", shop="browser: read\n") as c:
        c.site.pages["/vao"] = lambda site: SIGNS_IN
        await c.call("shop", NAVIGATE, "conv-2", url=c.site.url("/"))
        assert (await ask(c, url=c.site.url("/vao"))).status_code == 200
        window, windows, pool = c.windows.window("coach"), c.windows, c.pool
        await signed_in(window.context)
        profile = browser_root(c.home) / "coach"
        stop_all, left = pool.stop_all, []

        async def watched() -> None:
            # Read as the server's own shutdown gets to the crew's browsers, before the test
            # tidies anything: a window closed after them could no longer be asked.
            left.append((windows.window("coach"), len(window.context.pages), recalled(profile)))
            await stop_all()

        pool.stop_all = watched

    open_still, pages, written = left[0]
    assert open_still is None and pages == 0
    assert written is not None and written.keys() == {"127.0.0.1"}
    assert pool.reserved == set() and await gone(window.proxy.port)
    assert pool.running("shop") is None


async def test_while_the_window_is_open_the_agents_calls_are_told_a_person_is_signing_in(
    crew: Crew,
):
    await crew.call("coach", NAVIGATE, "conv-1", url=crew.site.url("/"))
    assert (await ask(crew)).status_code == 200

    for tool, args in ((NAVIGATE, {"url": crew.site.url("/don")}), (SNAPSHOT, {})):
        with pytest.raises(ToolError) as refusal:
            await crew.call("coach", tool, "conv-1", **args)
        assert str(refusal.value) == said.LOGIN_OPEN, tool
    # Its tabs went with the browser that was stopped for the window; asking starts none.
    assert await crew.call("coach", TABS, "conv-1") == told_to_a_model.TABS_NONE
    assert crew.pool.running("coach") is None and "GET /don" not in crew.site.seen
    # Another agent's browser is its own, and goes on.
    await crew.call("reader", NAVIGATE, "conv-9", url=crew.site.url("/dai"))
    assert (await crew.told("reader"))["running"] is True

    assert (await done(crew)).json() == {"closed": True}

    await crew.call("coach", NAVIGATE, "conv-1", url=crew.site.url("/don"))
    assert [tab["title"] for tab in (await crew.told("coach"))["tabs"]] == ["Đơn của tôi"]


async def test_a_window_that_closed_without_a_word_is_told_as_closed_and_the_agent_browses_on(
    crew: Crew,
):
    crew.windows.seconds = 0.3
    assert (await ask(crew)).status_code == 200
    # Nobody said they were done: it closed by itself.
    await until(lambda: crew.windows.window("coach") is None and not crew.pool.reserved)
    assert (await crew.told("coach"))["login"] == NO_WINDOW
    assert (await done(crew)).json() == {"closed": False}

    crew.windows.seconds = OPEN_SECONDS
    assert (await ask(crew)).status_code == 200
    (page,) = crew.windows.window("coach").context.pages
    await page.close()  # the person closed it themselves

    await until(lambda: crew.windows.window("coach") is None and not crew.pool.reserved)
    assert (await crew.told("coach"))["login"] == NO_WINDOW
    await crew.call("coach", NAVIGATE, "conv-1", url=crew.site.url("/don"))
    assert (await crew.told("coach"))["running"] is True


async def test_where_the_browser_may_be_signed_in_is_told_by_host_and_moment_and_nothing_more(
    crew: Crew,
):
    # Of a profile no browser ever closed on nothing is known, and nothing is made up.
    assert (await crew.told("coach"))["logins"] is None
    before = time.time()
    assert (await ask(crew, url=crew.site.url("/vao"))).status_code == 200
    await signed_in(crew.windows.window("coach").context)

    # Asked of the window while it is open.
    reply = await crew.client.get("/api/agents/coach/browser")
    (held,) = reply.json()["logins"]
    assert held.keys() == {"host", "until"} and held["host"] == "127.0.0.1"
    assert held["until"].endswith("+00:00")
    assert before + 3_590 < datetime.fromisoformat(held["until"]).timestamp() < time.time() + 3_610
    # Read from what was written as it closed.
    assert (await done(crew)).json() == {"closed": True}
    closed = await crew.client.get("/api/agents/coach/browser")
    assert (closed.json()["running"], closed.json()["logins"]) == (False, [held])
    # And asked of the agent's own browser once a call has started it, signed in as it was left.
    await crew.call("coach", NAVIGATE, "conv-1", url=crew.site.url("/"))
    running = await crew.client.get("/api/agents/coach/browser")
    assert (running.json()["running"], running.json()["logins"]) == (True, [held])
    assert "phien=bi-mat-123" in crew.site.heads[-1]["cookie"]

    # What signs the person in is in none of it: not the name of the cookie, not what it says.
    written = (browser_root(crew.home) / "coach" / FILE).read_text()
    for text in (reply.text, closed.text, running.text, written):
        assert not [secret for secret in SECRETS if secret in text]
    # Another agent's profile is another browser's: it is signed in nowhere.
    assert (await crew.told("reader"))["logins"] is None


async def test_an_agent_with_hosts_of_its_own_is_told_of_each_of_them_signed_in_or_not(
    tmp_path: Path, monkeypatch
):
    own = "browser: act\nbrowser_hosts: ['127.0.0.1', shop.example, '*.pay.example']\n"
    async with serving(tmp_path, monkeypatch, shop=own) as c:
        c.site.pages["/vao"] = lambda site: SIGNS_IN
        assert (await c.told("shop"))["logins"] is None
        assert (await ask(c, "shop", url=c.site.url("/vao"))).status_code == 200
        await signed_in(c.windows.window("shop").context)

        for still_open in (True, False):
            here, *others = (await c.told("shop"))["logins"]

            assert here["host"] == "127.0.0.1" and here["until"] is not None, still_open
            assert others == [
                {"host": "shop.example", "until": None},
                {"host": "*.pay.example", "until": None},
            ]
            assert (await done(c, "shop")).json() == {"closed": still_open}
