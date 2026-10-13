"""The browser tools an agent is given: which, by its `browser` key alone, and each of them
built for that agent and for no other."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
import pytest_asyncio

from my_agent_crew import texts_browser as t
from my_agent_crew.browser import kit as k
from my_agent_crew.browser.fence import room
from my_agent_crew.browser.pool import BrowserPool
from my_agent_crew.browser.tools import build_browser_tools
from my_agent_crew.config import Route
from my_agent_crew.config_browser import BrowserSettings
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.llm.provider import ProviderChain
from my_agent_crew.script.scope import only_reads
from tests.browser_tools import parts, ref_of, talking, world

pytestmark = pytest.mark.asyncio(loop_scope="module")

PAGES = {"/": "<title>Bộ</title><h1>Trang bộ</h1><button>Xem</button>"}
LOOKS = [
    "browser_navigate",
    "browser_snapshot",
    "browser_text",
    "browser_tabs",
    "browser_screenshot",
]


@pytest_asyncio.fixture(loop_scope="module", scope="module")
async def w(tmp_path_factory):
    async with world(tmp_path_factory.mktemp("set"), PAGES) as made:
        yield made


def on(**own) -> BrowserSettings:
    return BrowserSettings(enabled=True, **own)


def names(tools) -> list[str]:
    return [tool.name for tool in tools]


async def test_no_browser_on_the_machine_or_none_for_the_agent_is_no_tool(tmp_path: Path):
    pool = BrowserPool(tmp_path / "browser", on())

    assert build_browser_tools(None, "coach", on(mode="act"), tmp_path, 1_000) == []
    assert build_browser_tools(pool, "coach", on(), tmp_path, 1_000) == []
    assert build_browser_tools(pool, "coach", on(mode="off"), tmp_path, 1_000) == []
    off = BrowserSettings(enabled=False, mode="act")
    assert build_browser_tools(pool, "coach", off, tmp_path, 1_000) == []
    assert not (tmp_path / "browser").exists()  # and building tools starts nothing


async def test_an_agent_that_reads_gets_five_tools_and_one_that_acts_one_more(tmp_path: Path):
    pool = BrowserPool(tmp_path / "browser", on())

    read = build_browser_tools(pool, "coach", on(mode="read"), tmp_path, 1_000)
    act = build_browser_tools(pool, "coach", on(mode="act"), tmp_path, 1_000)

    assert names(read) == list(k.READ_TOOLS) == LOOKS
    assert names(act) == list(k.BROWSER_TOOLS) == [*LOOKS, "browser_act"]
    # Opening a page and doing something to one are the gate's; the rest only look, which is
    # also what lets a script call them.
    assert names(tool for tool in act if tool.requires_approval) == [k.NAVIGATE, k.ACT]
    assert names(tool for tool in act if only_reads(tool)) == LOOKS[1:]
    # Each tells the owner's screens it follows the agent's `browser` key and no list.
    assert [tool.to_dict() for tool in act] == [
        {
            "name": tool.name,
            "description": tool.description,
            "requires_approval": tool.requires_approval,
            "with_browser": True,
        }
        for tool in act
    ]
    assert not (tmp_path / "browser").exists()


@talking("set-own")
async def test_each_tool_is_built_for_the_agent_it_is_given_to(w):
    said = "thấy " + "".join(f"dòng-{n};" for n in range(2_000))
    provider = ScriptedProvider([completion(said)], name="vis")
    chain = ProviderChain({"vis": provider}, (Route("vis", "eyes"),))
    own = dataclasses.replace(w.pool.settings, mode="act", hosts=("shop.example",))
    made = build_browser_tools(
        w.pool, "purchases", own, w.workspace, 3_000, vision=chain, write_paths=("data", "notes")
    )
    tools = {tool.name: tool for tool in made}

    # The agent's own hosts decide what opening a page asks.
    here = w.site.url("/")
    assert tools[k.NAVIGATE].ask_when({"url": here}) == t.ASK_NAV_OUTSIDE.format(host="127.0.0.1")
    assert tools[k.NAVIGATE].allow_when({"url": "https://shop.example/don"}) is True

    # The browser started is this agent's, and the tab this conversation's.
    await tools[k.NAVIGATE].run({"url": here})
    assert w.tab("set-own", agent="purchases") is not None
    assert w.pool.running("coach") is None

    # What it was shown is cut at its own limit, and so is what a model read in a picture
    # that went to the chain it was given and into the first folder it is held to.
    outline = await tools[k.SNAPSHOT].run({})
    assert len(outline) <= 3_000
    shot = await tools[k.SCREENSHOT].run({})
    first = shot.output.splitlines()[0]
    (picture,) = (w.workspace / "data" / "screenshots").iterdir()
    assert first == t.SHOT_SAVED.format(label="t1", path=f"data/screenshots/{picture.name}")
    assert parts(shot.output)[1] == said[: room(3_000, first)]
    assert len(provider.requests) == 1 and shot.metered

    # And the one that acts judges the page by the same hosts.
    ref = ref_of(outline, "Xem")
    asked = tools[k.ACT].ask_when({"kind": "click", "ref": ref, "name": "Xem"})
    assert asked == t.ASK_OUTSIDE_HOSTS.format(kind="click", host="127.0.0.1")
    assert sorted(found.name for found in w.workspace.iterdir()) == ["data"]
