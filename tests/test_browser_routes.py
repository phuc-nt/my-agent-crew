"""An agent's browser as a person is told of it and as a person stops it: what the three
routes say of a browser that is down, up and in the middle of a call, and what an edit of the
agent or its removal does to the browser it left running. Real Chromium, reaching one local
server through the proxy."""

from __future__ import annotations

import asyncio
import functools
import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio

from my_agent_crew import texts
from my_agent_crew import texts_browser as told_to_a_model
from my_agent_crew import texts_browser_web as told_to_the_web
from my_agent_crew.activity.step_previews import outcome_preview
from my_agent_crew.agent.turn_context import reading_as
from my_agent_crew.browser.install import NO_BROWSER, Installed
from my_agent_crew.browser.kit import (
    ACT,
    BROWSER_TOOLS,
    NAVIGATE,
    READ_TOOLS,
    SCREENSHOT,
    SNAPSHOT,
)
from my_agent_crew.browser.pool import BrowserPool
from my_agent_crew.config_browser import browser_root
from my_agent_crew.server import browser_runtime, routes_browser
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.server.runtime_connections import channel_key, commit, prepare
from my_agent_crew.tools.registry import ToolError
from tests.browser_crew import HERE, ON, browser_tools, built, crew_home
from tests.browser_servers import Clock, Site, local_names, only

LONG_TITLE = "Tên trang rất dài " * 20
PAGES = {
    "/": "<title>Cửa hàng</title><h1>Đơn hàng</h1>",
    "/don": "<title>Đơn của tôi</title><p>Đơn số 7</p>",
    "/dai": f"<title>{LONG_TITLE}</title><p>dài</p>",
    "/khong": "<p>trang không có tên</p>",
    # Its first words come at once and its last ones long after: a call that is still going.
    "/cham": lambda site: (200, {}, ["<title>Chậm</title><p>đầu</p>", 6.0, "<p>cuối</p>"]),
}
# As `web/src/lib/screenshot-path.ts` reads it: the name the tool gives a picture is what
# ends the path, since a step's preview has no line ends left to tell by.
SHOT_LINE = re.compile(
    r"^Đã lưu ảnh chụp tab [a-z0-9_-]+ vào (.*?\d{8}T\d{6}Z-[a-z0-9_-]+\.(?:png|jpg))\."
)
DOWN = {
    "enabled": True,
    "installed": True,
    "running": False,
    "busy": False,
    "idle_seconds": None,
    "tabs": [],
}


@dataclass
class Crew:
    client: httpx.AsyncClient
    rt: Runtime
    site: Site
    home: Path
    clock: Clock
    env: dict[str, str]

    @property
    def pool(self) -> BrowserPool:
        return self.rt.browsers.pool

    async def call(self, agent_id: str, tool: str, conversation: str = "", **args: Any) -> str:
        """One call of an agent's own tool, as a turn of that conversation makes it; as a
        scheduled run makes it where no conversation is named."""
        run = self.rt.deps_for(agent_id).tools.get(tool).run
        if not conversation:
            return await run(args)
        with reading_as(conversation):
            return await run(args)

    async def told(self, agent_id: str) -> dict[str, Any]:
        reply = await self.client.get(f"/api/agents/{agent_id}/browser")
        assert reply.status_code == 200, reply.text
        return reply.json()

    def going(self, agent_id: str, conversation: str) -> asyncio.Future[str]:
        """A call that will not end by itself for seconds."""
        slow = self.call(agent_id, NAVIGATE, conversation, url=self.site.url("/cham"))
        return asyncio.ensure_future(slow)


@asynccontextmanager
async def serving(
    root: Path, monkeypatch, eyes: bool = False, **agents: str
) -> AsyncIterator[Crew]:
    """A crew served on the test's own loop, whose browsers reach one local server. With
    `eyes` the crew has a model that reads pictures."""
    site, clock = Site(PAGES), Clock()
    monkeypatch.setattr(browser_runtime, "installed", lambda channel, env: HERE)
    reaching = functools.partial(BrowserPool, resolver=local_names, allow=only(site), clock=clock)
    monkeypatch.setattr(browser_runtime, "BrowserPool", reaching)
    env = crew_home(root, **agents) | ({"MY_AGENT_VISION_ROUTES": "fake:echo"} if eyes else {})
    rt = built(env)
    app = create_app(rt, schedule=False)
    try:
        async with app.router.lifespan_context(app):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as web:
                yield Crew(web, rt, site, root / "home", clock, env)
    finally:
        await rt.browsers.pool.stop_all()
        site.close()


@pytest_asyncio.fixture
async def crew(tmp_path: Path, monkeypatch) -> AsyncIterator[Crew]:
    agents = {"coach": "browser: act\n", "reader": "browser: read\n", "plain": "description: x\n"}
    async with serving(tmp_path, monkeypatch, **agents) as made:
        yield made


async def until(done: Callable[[], Any], seconds: float = 10.0) -> None:
    async with asyncio.timeout(seconds):
        while not done():
            await asyncio.sleep(0.01)


def failed_words() -> str:
    """How a navigation that lost its page under it ends: as a page that would not open."""
    return told_to_a_model.NAV_FAILED.split("{error}")[0]


async def test_a_browser_that_is_down_is_told_so_and_asking_starts_nothing(crew: Crew):
    assert await crew.told("coach") == {"mode": "act", **DOWN}
    assert await crew.told("reader") == {"mode": "read", **DOWN}
    for without in ("plain", "default"):
        assert await crew.told(without) == {"mode": "off", **DOWN}, without

    # Nor does stopping one that is down, or closing a tab of it.
    reply = await crew.client.post("/api/agents/coach/browser/stop")
    assert (reply.status_code, reply.json()) == (200, {"stopped": False})
    reply = await crew.client.delete("/api/agents/coach/browser/tabs/1")
    assert (reply.status_code, reply.json()) == (404, {"detail": told_to_the_web.TAB_UNKNOWN})

    assert all(crew.pool.running(agent_id) is None for agent_id in crew.rt.agents)
    assert not browser_root(crew.home).exists()


async def test_the_crews_tool_list_marks_the_browser_tools_as_the_browser_keys_to_give(
    crew: Crew,
):
    listed = {tool["name"]: tool for tool in (await crew.client.get("/api/tools")).json()}

    # The mark is what a screen tells them apart by: no allow-list brings one, so a cell
    # that is empty is the agent's `browser` key and nothing a list or an API key explains.
    assert [name for name, tool in listed.items() if "with_browser" in tool] == sorted(
        BROWSER_TOOLS
    )
    for name in BROWSER_TOOLS:
        assert listed[name]["with_browser"] is True, name
        assert listed[name]["optional"] is False, name
        assert "with_reads" not in listed[name] and "with_mcp" not in listed[name], name
    assert {name: listed[name]["agents"] for name in READ_TOOLS} == dict.fromkeys(
        READ_TOOLS, ["coach", "reader"]
    )
    assert listed[ACT]["agents"] == ["coach"]
    assert [name for name in BROWSER_TOOLS if listed[name]["requires_approval"]] == [NAVIGATE, ACT]
    # And none of them is an agent's list's to give, whatever the agent's key says.
    for agent in (await crew.client.get("/api/agents")).json():
        assert not set(agent["listable_tools"]) & set(BROWSER_TOOLS), agent["id"]


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/browser"), ("POST", "/browser/stop"), ("DELETE", "/browser/tabs/1")],
)
async def test_an_agent_the_crew_does_not_have_is_a_404(crew: Crew, method: str, path: str):
    reply = await crew.client.request(method, f"/api/agents/ghost{path}")

    assert reply.status_code == 404
    assert reply.json() == {"detail": texts.AGENT_UNKNOWN.format(agent_id="ghost")}
    assert not browser_root(crew.home).exists()


async def test_a_tab_is_named_by_its_number_alone(crew: Crew):
    reply = await crew.client.delete("/api/agents/coach/browser/tabs/t1")

    assert reply.status_code == 422


async def test_a_running_browser_is_told_by_its_tabs_last_used_first(crew: Crew):
    crew.clock.now = 100.0
    await crew.call("coach", NAVIGATE, "conv-1", url=crew.site.url("/"))
    crew.clock.now = 110.0
    await crew.call("coach", NAVIGATE, "conv-2", url=crew.site.url("/don", host="localhost"))
    crew.clock.now = 120.0
    await crew.call("coach", NAVIGATE, url=crew.site.url("/khong"))  # a scheduled run's
    crew.clock.now = 130.0
    await crew.call("coach", SNAPSHOT, "conv-1")
    crew.clock.now = 147.9

    told = await crew.told("coach")

    first, second, job = (crew.pool.peek("coach", owner) for owner in ("conv-1", "conv-2", "job"))
    assert len({first.id, second.id, job.id}) == 3
    assert told == {
        "mode": "act",
        "enabled": True,
        "installed": True,
        "running": True,
        "busy": False,
        "idle_seconds": 17,
        "tabs": [
            {
                "id": first.id,
                "label": first.label,
                "conversation_id": "conv-1",
                "host": "127.0.0.1",
                "title": "Cửa hàng",
                "idle_seconds": 17,
                "busy": False,
            },
            {
                "id": job.id,
                "label": job.label,
                "conversation_id": None,
                "host": "127.0.0.1",
                "title": "",
                "idle_seconds": 27,
                "busy": False,
            },
            {
                "id": second.id,
                "label": second.label,
                "conversation_id": "conv-2",
                "host": "localhost",
                "title": "Đơn của tôi",
                "idle_seconds": 37,
                "busy": False,
            },
        ],
    }
    # One agent's browser is not another's: asking after it did not start theirs either.
    assert await crew.told("reader") == {"mode": "read", **DOWN}
    assert sorted(path.name for path in browser_root(crew.home).iterdir()) == ["coach"]

    connections = (await crew.client.get("/api/connections")).json()
    assert connections["browser"] == {
        "enabled": True,
        "channel": "chromium",
        "installed": True,
        "version": HERE.version,
        "missing": "",
        "install_command": "",
        "running": ["coach"],
    }


async def test_a_tab_is_told_by_its_host_and_title_and_never_by_its_address(crew: Crew):
    address = crew.site.url("/don?token=bi-mat-123&next=/tra-tien#o-day")
    await crew.call("reader", NAVIGATE, "conv-1", url=address)
    await crew.call("reader", NAVIGATE, "conv-2", url=crew.site.url("/dai"))

    reply = await crew.client.get("/api/agents/reader/browser")

    for part in ("bi-mat-123", "token", "tra-tien", "o-day", "/don", str(crew.site.port)):
        assert part not in reply.text, part
    long, signed_in = reply.json()["tabs"]
    assert (signed_in["host"], signed_in["title"]) == ("127.0.0.1", "Đơn của tôi")
    assert long["title"] == LONG_TITLE[:200] and len(long["title"]) == 200


class Page:
    """A page that says its title late, not at all, or in too many words."""

    def __init__(self, title: str | Exception, after: float = 0.0) -> None:
        self.answer, self.after, self.url = title, after, "about:blank"

    async def title(self) -> str:
        await asyncio.sleep(self.after)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_idle_time_is_the_whole_seconds_gone_by_and_never_less_than_none():
    assert routes_browser._idle(147.9, 130.0) == 17
    # A tab somebody used while the titles were being read is not told as used in the future.
    assert routes_browser._idle(10.0, 12.5) == 0


@pytest.mark.parametrize(
    ("config", "found", "enabled", "installed"),
    [("", HERE, False, True), (ON, Installed(False, missing=NO_BROWSER), True, False)],
)
async def test_an_agent_whose_machine_has_no_browser_to_start_is_told_which_part_is_missing(
    tmp_path: Path, monkeypatch, config: str, found: Installed, enabled: bool, installed: bool
):
    monkeypatch.setattr(browser_runtime, "installed", lambda channel, env: found)
    rt = built(crew_home(tmp_path, config=config, coach="browser: act\n"))
    app = create_app(rt, schedule=False)

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as web:
            told = await web.get("/api/agents/coach/browser")
            stopped = await web.post("/api/agents/coach/browser/stop")
            closed = await web.delete("/api/agents/coach/browser/tabs/1")

    # Its own file still asks for one: the mode is the agent's, the reason is the machine's.
    assert told.json() == {"mode": "act", **DOWN, "enabled": enabled, "installed": installed}
    assert (stopped.status_code, stopped.json()) == (200, {"stopped": False})
    assert (closed.status_code, closed.json()) == (404, {"detail": told_to_the_web.TAB_UNKNOWN})
    assert rt.browsers.pool is None and browser_tools(rt, "coach") == []


async def test_a_page_that_cannot_say_its_title_is_told_without_one(monkeypatch):
    assert routes_browser.TITLE_SECONDS == 1.0
    monkeypatch.setattr(routes_browser, "TITLE_SECONDS", 0.05)

    assert await routes_browser._title(Page("Đơn hàng")) == "Đơn hàng"
    assert await routes_browser._title(Page("Đơn hàng", after=0.01)) == "Đơn hàng"
    assert await routes_browser._title(Page("Đơn hàng", after=30)) == ""
    assert await routes_browser._title(Page(RuntimeError("Target page has been closed"))) == ""
    assert await routes_browser._title(Page("x" * 500)) == "x" * 200


async def test_a_call_in_flight_is_told_as_busy_and_ends_when_a_person_closes_its_tab(crew: Crew):
    await crew.call("coach", NAVIGATE, "conv-1", url=crew.site.url("/"))
    await crew.call("coach", NAVIGATE, "conv-2", url=crew.site.url("/don"))
    session = crew.pool.running("coach")
    slow = crew.going("coach", "conv-1")
    await until(lambda: crew.pool.peek("coach", "conv-1").lock.locked())

    told = await crew.told("coach")
    assert told["busy"] is True
    by_owner = {tab["conversation_id"]: tab for tab in told["tabs"]}
    assert (by_owner["conv-1"]["busy"], by_owner["conv-2"]["busy"]) == (True, False)

    reply = await crew.client.delete(f"/api/agents/coach/browser/tabs/{by_owner['conv-1']['id']}")

    assert (reply.status_code, reply.json()) == (200, {"closed": by_owner["conv-1"]["id"]})
    with pytest.raises(ToolError) as refusal:
        await asyncio.wait_for(slow, 5)
    assert str(refusal.value).startswith(failed_words())
    # The browser and the other conversation's tab are as they were.
    told = await crew.told("coach")
    assert crew.pool.running("coach") is session
    assert (told["running"], told["busy"]) == (True, False)
    assert [tab["conversation_id"] for tab in told["tabs"]] == ["conv-2"]
    # Closing it twice says it is gone, and so does a number no tab ever had.
    for gone in (by_owner["conv-1"]["id"], 9_999):
        reply = await crew.client.delete(f"/api/agents/coach/browser/tabs/{gone}")
        assert (reply.status_code, reply.json()) == (404, {"detail": told_to_the_web.TAB_UNKNOWN})
    # A tab is closed in the browser of the agent the address names, and in no other's.
    reply = await crew.client.delete(f"/api/agents/reader/browser/tabs/{told['tabs'][0]['id']}")
    assert reply.status_code == 404 and crew.pool.running("reader") is None
    assert [tab["conversation_id"] for tab in (await crew.told("coach"))["tabs"]] == ["conv-2"]
    # And the conversation that lost its tab opens another with its next call.
    await crew.call("coach", NAVIGATE, "conv-1", url=crew.site.url("/don"))
    assert [tab["conversation_id"] for tab in (await crew.told("coach"))["tabs"]] == [
        "conv-1",
        "conv-2",
    ]


async def test_stopping_ends_the_call_in_flight_keeps_the_logins_and_lets_the_next_call_start_it(
    crew: Crew,
):
    await crew.call("coach", NAVIGATE, "conv-1", url=crew.site.url("/"))
    await crew.call("reader", NAVIGATE, "conv-9", url=crew.site.url("/"))
    first, other = crew.pool.running("coach"), crew.pool.running("reader")
    profile = browser_root(crew.home) / "coach"
    slow = crew.going("coach", "conv-1")
    await until(lambda: first.busy)

    reply = await crew.client.post("/api/agents/coach/browser/stop")

    assert (reply.status_code, reply.json()) == (200, {"stopped": True})
    with pytest.raises(ToolError) as refusal:
        await asyncio.wait_for(slow, 5)
    assert str(refusal.value).startswith(failed_words())
    assert crew.pool.running("coach") is None
    assert await crew.told("coach") == {"mode": "act", **DOWN}
    # What it was signed in to is still in its folder, and nobody else's browser went.
    assert profile.is_dir() and any(profile.iterdir())
    assert crew.pool.running("reader") is other and (await crew.told("reader"))["running"]
    reply = await crew.client.post("/api/agents/coach/browser/stop")
    assert (reply.status_code, reply.json()) == (200, {"stopped": False})

    await crew.call("coach", NAVIGATE, "conv-1", url=crew.site.url("/don"))

    again = crew.pool.running("coach")
    assert again is not None and again is not first
    assert [tab["title"] for tab in (await crew.told("coach"))["tabs"]] == ["Đơn của tôi"]


async def test_an_agent_taken_off_the_browser_has_the_one_it_left_running_stopped(crew: Crew):
    await crew.call("coach", NAVIGATE, "conv-1", url=crew.site.url("/"))
    await crew.call("reader", NAVIGATE, "conv-9", url=crew.site.url("/"))
    session, other = crew.pool.running("coach"), crew.pool.running("reader")

    # Fewer rights, or a key that is not the browser's: the browser it has up is still its own.
    for profile in ({"browser": "read", "browser_hosts": ["shop.example"]}, {"description": "x"}):
        reply = await crew.client.patch("/api/agents/coach", json={"profile": profile})
        assert reply.status_code == 200, reply.text
        assert crew.pool.running("coach") is session
        assert browser_tools(crew.rt, "coach") == list(READ_TOOLS)
    told = await crew.told("coach")
    assert (told["mode"], told["running"], len(told["tabs"])) == ("read", True, 1)

    reply = await crew.client.patch("/api/agents/coach", json={"profile": {"browser": "off"}})

    assert reply.status_code == 200, reply.text
    assert crew.pool.running("coach") is None
    assert browser_tools(crew.rt, "coach") == []
    assert await crew.told("coach") == {"mode": "off", **DOWN}
    # Its logins wait for the day it is given the browser back; the others' browsers stay up.
    assert (browser_root(crew.home) / "coach").is_dir()
    assert crew.pool.running("reader") is other


async def test_a_removed_agent_takes_its_browser_and_what_it_was_signed_in_to_with_it(crew: Crew):
    await crew.call("coach", NAVIGATE, "conv-1", url=crew.site.url("/"))
    await crew.call("reader", NAVIGATE, "conv-9", url=crew.site.url("/"))
    other = crew.pool.running("reader")
    assert sorted(path.name for path in browser_root(crew.home).iterdir()) == ["coach", "reader"]

    reply = await crew.client.delete("/api/agents/coach")

    assert reply.status_code in (200, 204), reply.text
    assert crew.pool.running("coach") is None
    assert sorted(path.name for path in browser_root(crew.home).iterdir()) == ["reader"]
    assert crew.pool.running("reader") is other
    assert (await crew.client.get("/api/agents/coach/browser")).status_code == 404
    assert (await crew.client.get("/api/connections")).json()["browser"]["running"] == ["reader"]


async def test_a_turn_still_running_when_its_agent_loses_the_browser_browses_no_more(crew: Crew):
    """A turn keeps the tools it began with. Those of an agent taken off the browser, or of
    one that was removed, start no browser: what the owner just stopped stays stopped."""
    held = {a: crew.rt.deps_for(a).tools.get(NAVIGATE).run for a in ("coach", "reader")}

    async def go(agent_id: str) -> str:
        with reading_as("conv-1"):
            return await held[agent_id]({"url": crew.site.url("/don")})

    async def refused(agent_id: str) -> str:
        with pytest.raises(ToolError) as refusal:
            await go(agent_id)
        return str(refusal.value)

    await go("coach"), await go("reader")

    reply = await crew.client.patch("/api/agents/coach", json={"profile": {"browser": "off"}})

    assert reply.status_code == 200, reply.text
    assert await refused("coach") == told_to_a_model.BROWSER_GONE
    assert crew.pool.running("coach") is None
    assert await crew.told("coach") == {"mode": "off", **DOWN}
    # Given the browser back, the agent's next turn browses, signed in as before. The turn
    # that was running when it lost the browser is not given it back.
    reply = await crew.client.patch("/api/agents/coach", json={"profile": {"browser": "act"}})
    assert reply.status_code == 200, reply.text
    await crew.call("coach", NAVIGATE, "conv-2", url=crew.site.url("/"))
    assert crew.pool.running("coach") is not None
    assert await refused("coach") == told_to_a_model.BROWSER_GONE

    reply = await crew.client.delete("/api/agents/reader")

    assert reply.status_code in (200, 204), reply.text
    assert await refused("reader") == told_to_a_model.BROWSER_GONE
    assert crew.pool.running("reader") is None
    assert sorted(path.name for path in browser_root(crew.home).iterdir()) == ["coach"]


async def test_an_agent_its_file_took_off_the_browser_has_it_stopped_when_the_crew_is_built_again(
    crew: Crew,
):
    held = {a: crew.rt.deps_for(a).tools.get(NAVIGATE).run for a in ("coach", "reader")}
    await crew.call("coach", NAVIGATE, "conv-1", url=crew.site.url("/"))
    await crew.call("reader", NAVIGATE, "conv-9", url=crew.site.url("/"))
    other = crew.pool.running("reader")
    own = crew.home / "agents" / "coach" / "agent.yaml"
    own.write_text("name: coach\nbrowser: 'off'\n", encoding="utf-8")

    # A key or the routes saved builds every running agent from its file again.
    await commit(crew.rt, prepare(crew.rt, crew.env), channel_key(crew.rt.agents, crew.env))

    assert browser_tools(crew.rt, "coach") == []
    assert crew.pool.running("coach") is None
    assert (browser_root(crew.home) / "coach").is_dir()
    with reading_as("conv-1"), pytest.raises(ToolError) as refusal:
        await held["coach"]({"url": crew.site.url("/don")})
    assert str(refusal.value) == told_to_a_model.BROWSER_GONE
    # An agent that still has the browser keeps the one it had up, and a turn of its that
    # was running goes on with it.
    assert crew.pool.running("reader") is other
    with reading_as("conv-9"):
        await held["reader"]({"url": crew.site.url("/don")})
    assert [tab["title"] for tab in (await crew.told("reader"))["tabs"]] == ["Đơn của tôi"]


async def test_an_agent_that_joins_or_is_built_again_while_served_browses_through_the_one_pool(
    crew: Crew,
):
    made = {"agent_id": "shop", "profile": {"browser": "act", "browser_hosts": ["127.0.0.1"]}}
    reply = await crew.client.post("/api/agents", json=made)
    assert reply.status_code == 201, reply.text
    copied = crew.home / "agents" / "copied"
    copied.mkdir()
    (copied / "agent.yaml").write_text("name: copied\nbrowser: read\n", encoding="utf-8")
    reply = await crew.client.post("/api/agents/reload")
    assert (reply.status_code, reply.json()) == (200, {"added": ["copied"]})
    # A key or the routes saved builds every running agent from its file again: one edited by
    # hand since is read with the rest.
    own = crew.home / "agents" / "coach" / "agent.yaml"
    own.write_text("name: coach\nbrowser: read\n", encoding="utf-8")
    await commit(crew.rt, prepare(crew.rt, crew.env), channel_key(crew.rt.agents, crew.env))

    held = {agent_id: browser_tools(crew.rt, agent_id) for agent_id in crew.rt.agents}
    assert held == {
        "default": [],
        "coach": list(READ_TOOLS),
        "reader": list(READ_TOOLS),
        "plain": [],
        "shop": list(BROWSER_TOOLS),
        "copied": list(READ_TOOLS),
    }
    for agent_id, mode in (("shop", "act"), ("copied", "read"), ("coach", "read")):
        assert await crew.told(agent_id) == {"mode": mode, **DOWN}
        await crew.call(agent_id, NAVIGATE, "conv-1", url=crew.site.url("/don"))
        assert [tab["title"] for tab in (await crew.told(agent_id))["tabs"]] == ["Đơn của tôi"]
    assert (await crew.client.get("/api/connections")).json()["browser"]["running"] == [
        "coach",
        "copied",
        "shop",
    ]
    assert sorted(path.name for path in browser_root(crew.home).iterdir()) == [
        "coach",
        "copied",
        "shop",
    ]


async def test_a_picture_goes_where_the_agents_own_file_keeps_its_writing_and_is_read_for_it(
    tmp_path: Path, monkeypatch
):
    agents = {"held": "browser: read\nwrite_paths: [out]\n", "free": "browser: read\n"}
    async with serving(tmp_path, monkeypatch, eyes=True, **agents) as c:
        for agent_id, folder in (("held", "out/screenshots"), ("free", "screenshots")):
            await c.call(agent_id, NAVIGATE, "conv-1", url=c.site.url("/"))

            answer = await c.call(agent_id, SCREENSHOT, "conv-1")

            workspace = c.rt.deps_for(agent_id).agent.workspace
            (picture,) = (workspace / folder).iterdir()
            label = c.pool.peek(agent_id, "conv-1").label
            saved = told_to_a_model.SHOT_SAVED.format(label=label, path=f"{folder}/{picture.name}")
            said = answer.output.splitlines()
            assert said[0] == saved and len(said) > 1, agent_id
            # Read by the crew's model for pictures, and counted as a call of it.
            assert told_to_a_model.SHOT_NO_VISION not in answer.output
            assert not any(line.startswith("Không đọc được ảnh") for line in said)
            assert answer.metered is True
            assert [path.name for path in workspace.rglob("*.png")] == [picture.name]
            # The web draws the picture from the path in that line, read the one way from
            # the whole answer and from what a run's step keeps of it, which is one line cut
            # short. The route that serves a workspace file gives the picture as an image.
            (shown,) = SHOT_LINE.findall(answer.output)
            assert SHOT_LINE.findall(outcome_preview(answer.output, True)) == [shown]
            assert shown == f"{folder}/{picture.name}"
            served = await c.client.get(f"/api/agents/{agent_id}/files", params={"path": shown})
            assert served.status_code == 200, agent_id
            assert served.headers["content-type"] == "image/png"
            assert served.content == picture.read_bytes()


async def test_a_server_that_goes_down_leaves_no_browser_up(tmp_path: Path, monkeypatch):
    async with serving(tmp_path, monkeypatch, coach="browser: act\n", shop="browser: read\n") as c:
        await c.call("coach", NAVIGATE, "conv-1", url=c.site.url("/"))
        await c.call("shop", NAVIGATE, "conv-2", url=c.site.url("/"))
        contexts = [c.pool.running(agent_id).context for agent_id in ("coach", "shop")]
        stop_all, left = c.pool.stop_all, []

        async def watched() -> None:
            await stop_all()
            # Read as the server's own shutdown ends, before the test tidies anything.
            left.extend(agent_id for agent_id in ("coach", "shop") if c.pool.running(agent_id))
            left.append("asked")

        c.pool.stop_all = watched
        pool = c.pool

    assert left[0] == "asked"
    assert all(pool.running(agent_id) is None for agent_id in ("coach", "shop"))
    assert [len(context.pages) for context in contexts] == [0, 0]
