"""The crew's browsers as the server holds them: the folder closed in every case, a pool only
where the machine turns the browser on and has one to start, each agent given the tools its
own `browser` key asks for, and the loop that stops the browsers nobody uses."""

from __future__ import annotations

import asyncio
import importlib
import logging
import shutil
from collections import Counter
from pathlib import Path

import pytest

from my_agent_crew import texts
from my_agent_crew.browser.install import NO_BROWSER, NO_PACKAGE, Installed
from my_agent_crew.browser.kit import ACT, BROWSER_TOOLS, NAVIGATE, READ_TOOLS
from my_agent_crew.browser.pool import BrowserPool
from my_agent_crew.config import load_settings
from my_agent_crew.config_browser import BrowserSettings, browser_root, profile_dir
from my_agent_crew.script.scope import callable_tools
from my_agent_crew.server import browser_runtime
from my_agent_crew.server.app import create_app
from my_agent_crew.server.browser_runtime import Browsers, build_browsers, reap_loop
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.tools.pdf_texts import PDF_NOT_FOUND
from my_agent_crew.tools.private_paths import is_private
from tests.browser_crew import HERE, ON, browser_tools, built
from tests.browser_crew import crew_home as crew
from tests.test_shell_network_sandbox import needs_sandbox
from tests.test_tools_pdf import typeset

LOG = "my_agent_crew.server.browser_runtime"
ASSEMBLY = "my_agent_crew.server.tool_assembly"
SCRIPT = "tool_script"


def told_by(caplog, logger: str) -> list[tuple[str, str]]:
    """What one module logged, as its level and its words."""
    return [(r.levelname, r.getMessage()) for r in caplog.records if r.name == logger]


@pytest.fixture
def machine(monkeypatch):
    """What the machine has to start a browser with: the pinned Chromium, until a test says
    something is missing. No test here starts one."""

    def has(found: Installed) -> None:
        monkeypatch.setattr(browser_runtime, "installed", lambda channel, env: found)

    has(HERE)
    return has


def test_each_agent_is_given_the_browser_tools_its_own_key_asks_for(tmp_path: Path, machine):
    env = crew(
        tmp_path,
        plain="description: no key\n",
        off="browser: 'off'\n",
        reader="browser: read\n",
        doer="browser: act\nbrowser_hosts: [shop.example]\n",
    )

    rt = built(env)

    assert browser_tools(rt, "reader") == list(READ_TOOLS)
    assert browser_tools(rt, "doer") == list(BROWSER_TOOLS)
    for without in ("default", "plain", "off"):
        assert browser_tools(rt, without) == [], without
    # One pool for the crew, and building a crew starts nothing.
    assert isinstance(rt.browsers.pool, BrowserPool)
    assert rt.browsers.pool.root == browser_root(tmp_path / "home")
    assert not browser_root(tmp_path / "home").exists()


def test_the_master_is_given_them_by_its_own_file_like_any_agent(tmp_path: Path, machine):
    rt = built(crew(tmp_path, master="browser: read\n", coach="description: x\n"))

    assert browser_tools(rt, "default") == list(READ_TOOLS)
    assert browser_tools(rt, "coach") == []


def test_a_machine_that_leaves_the_browser_off_gives_no_agent_a_tool(
    tmp_path: Path, machine, caplog
):
    with caplog.at_level(logging.WARNING, logger=LOG):
        rt = built(crew(tmp_path, config="", doer="browser: act\n"))

    assert browser_tools(rt, "doer") == []
    assert rt.browsers.pool is None
    assert rt.browsers.status(rt.agents) == {
        "enabled": False,
        "channel": "chromium",
        "installed": True,
        "version": HERE.version,
        "missing": "",
        "install_command": "",
        "running": [],
    }
    assert told_by(caplog, LOG) == []  # a browser nobody asked for is not worth a line


@pytest.mark.parametrize(
    ("config", "found", "missing", "command"),
    [
        (ON, Installed(False, missing=NO_PACKAGE), "the playwright package", "uv sync"),
        (
            ON,
            Installed(False, "153.0", NO_BROWSER),
            "the browser itself",
            "uv run playwright install chromium",
        ),
        # The machine's own Chrome is its owner's to install: there is no command to give.
        (ON + "browser_channel: chrome\n", Installed(False, missing=NO_BROWSER), "itself", ""),
    ],
)
def test_a_browser_turned_on_and_not_there_is_one_warning_and_a_server_that_starts(
    tmp_path: Path, machine, caplog, config, found, missing, command
):
    machine(found)
    env = crew(tmp_path, config=config, master="browser: read\n", doer="browser: act\n")

    with caplog.at_level(logging.WARNING, logger=LOG):
        rt = built(env)

    assert browser_tools(rt, "doer") == [] and browser_tools(rt, "default") == []
    assert rt.browsers.pool is None
    ((level, told),) = told_by(caplog, LOG)  # one line for the machine, not one an agent
    assert level == "WARNING"
    assert told.startswith("browser_enabled is set but ") and missing in told
    assert told.endswith(f" (run: {command})" if command else "browser tool")
    status = rt.browsers.status(rt.agents)
    assert (status["enabled"], status["installed"]) == (True, False)
    assert (status["missing"], status["version"]) == (found.missing, found.version)
    assert status["install_command"] == command and status["running"] == []


def test_the_tools_list_neither_brings_a_browser_tool_nor_takes_one_away(
    tmp_path: Path, machine, caplog
):
    env = crew(
        tmp_path,
        narrow="tools: [workspace_read]\nbrowser: act\n",
        named="tools: [workspace_read, browser_act]\nbrowser: read\n",
        bare="tools: [workspace_read, browser_navigate]\n",
    )

    with caplog.at_level(logging.WARNING, logger=ASSEMBLY):
        rt = built(env)

    # `tool_script` comes to whoever holds a tool that reads, after everything else.
    assert rt.deps_for("narrow").tools.names() == ["workspace_read", *BROWSER_TOOLS, SCRIPT]
    assert rt.deps_for("named").tools.names() == ["workspace_read", *READ_TOOLS, SCRIPT]
    assert rt.deps_for("bare").tools.names() == ["workspace_read", SCRIPT]
    # A list that names one is told what does bring it, whether or not the agent has it.
    told = sorted(told_by(caplog, ASSEMBLY))
    key = "the browser tools come with the agent's `browser` key"
    assert [level for level, _ in told] == ["WARNING", "WARNING"]
    assert told[0][1].startswith(f"agent bare: tools lists {NAVIGATE}, ")
    assert told[1][1].startswith(f"agent named: tools lists {ACT}, ")
    assert told[0][1].endswith(key) and told[1][1].endswith(key)
    # And no list is offered one to tick: the key is the only switch.
    for agent_id in ("narrow", "named", "bare", "default"):
        offered = rt.deps_for(agent_id).listable_tools
        assert "workspace_read" in offered and not set(offered) & set(BROWSER_TOOLS), agent_id


def test_a_script_calls_the_tools_that_only_look_and_a_gated_one_the_rest(tmp_path: Path, machine):
    rt = built(crew(tmp_path, doer="browser: act\n"))
    held = rt.deps_for("doer").tools

    def reached(**scope) -> set[str]:
        return {tool.name for tool in callable_tools(held, **scope)} & set(BROWSER_TOOLS)

    assert reached() == set(READ_TOOLS) - {NAVIGATE}
    assert reached(gated=True) == set(BROWSER_TOOLS)


@pytest.mark.parametrize("config", [ON, ""])
async def test_the_folder_is_closed_to_the_file_tools_with_the_browser_on_or_off(
    tmp_path: Path, machine, config
):
    home = tmp_path / "home"
    env = crew(tmp_path, config=config, coach="description: x\n", wide=f"workspace: {home}\n")
    (browser_root(home) / "coach").mkdir(parents=True)
    (home / "inbox").mkdir()
    kept = typeset(browser_root(home) / "coach" / "saved.pdf", ["khoa bimat"])
    sent = typeset(home / "inbox" / "sent.pdf", ["thu cua chu"])

    rt = built(env)

    assert is_private(kept) and is_private(kept.parent.parent) and not is_private(sent)
    # The crew home is a root of the tool that reads a PDF, for what a person sent: it reads
    # the one in the inbox and is told nothing is there for the one a browser kept.
    for agent_id in ("default", "coach"):
        read = rt.deps_for(agent_id).tools
        answer = await read.execute("pdf_read", {"path": str(sent)})
        assert answer.ok and "thu cua chu" in answer.output, agent_id
        answer = await read.execute("pdf_read", {"path": str(kept)})
        assert not answer.ok and "bimat" not in answer.output, agent_id
        assert PDF_NOT_FOUND.format(path=kept) in answer.output, agent_id
    # An agent whose workspace is the crew home itself walks everything else in it.
    wide = rt.deps_for("wide").tools
    listed = await wide.execute("workspace_list", {"path": "inbox"})
    assert listed.ok and "sent.pdf" in listed.output
    for name, args in (
        ("workspace_list", {"path": "browser"}),
        ("workspace_list", {"path": "browser/coach"}),
        ("workspace_read", {"path": "browser/coach/saved.pdf"}),
        ("workspace_write", {"path": "browser/coach/Preferences", "content": "{}"}),
    ):
        answer = await wide.execute(name, args)
        assert not answer.ok and texts.WORKSPACE_PRIVATE in answer.output, (name, args)
    assert sorted(p.name for p in kept.parent.iterdir()) == ["saved.pdf"]


def test_a_runtime_made_around_a_few_agents_closes_the_folder_too(deps_factory, tmp_path: Path):
    deps = deps_factory()

    rt = Runtime.single(deps)

    assert rt.browsers.pool is None and not rt.browsers.settings.enabled
    assert rt.browsers.root == browser_root(deps.settings.home)
    assert is_private(deps.settings.home / "browser" / "default" / "Cookies")


@needs_sandbox
async def test_a_confined_shell_is_kept_out_of_the_folder_and_an_open_one_is_not_sandboxed(
    tmp_path: Path, machine
):
    env = crew(tmp_path, closed="shell_network: false\nbrowser: act\n", open="browser: act\n")
    kept = browser_root(tmp_path / "home").resolve() / "closed" / "Cookies"
    kept.parent.mkdir(parents=True)
    kept.write_text("khoa = bimat\n", encoding="utf-8")
    rt = built(env)

    async def cat(agent_id: str) -> tuple[bool, str]:
        answer = await rt.deps_for(agent_id).tools.execute("shell_run", {"command": f"cat {kept}"})
        return answer.ok, answer.output

    ok, refused = await cat("closed")
    assert not ok and "bimat" not in refused and "Operation not permitted" in refused
    before, after = texts.SHELL_PRIVATE_DENIED.split("{paths}")
    assert before in refused and after in refused
    # A shell nothing confines reads every file its user can, this one among them: giving
    # an agent a browser does not sandbox its shell, and the docs say so.
    ok, read = await cat("open")
    assert ok and "bimat" in read


def test_build_browsers_closes_the_folder_before_it_looks_for_a_browser(
    tmp_path: Path, monkeypatch
):
    seen: list[bool] = []
    home = tmp_path / "home"

    def look(channel: str, env) -> Installed:
        seen.append(is_private(home / "browser" / "x"))
        return Installed(False, missing=NO_PACKAGE)

    monkeypatch.setattr(browser_runtime, "installed", look)
    settings = load_settings(env={"MY_AGENT_HOME": str(home)})

    browsers = build_browsers(settings, {})

    assert seen == [True]
    assert (browsers.root, browsers.settings, browsers.pool) == (
        home / "browser",
        settings.browser,
        None,
    )


def test_the_pool_is_made_from_the_machines_settings_and_looks_for_the_channel_it_names(
    tmp_path: Path, monkeypatch
):
    asked: list[tuple[str, dict]] = []

    def look(channel: str, env) -> Installed:
        asked.append((channel, dict(env)))
        return HERE

    monkeypatch.setattr(browser_runtime, "installed", look)
    env = crew(tmp_path, config=ON + "browser_channel: chrome\nbrowser_max_tabs: 2\n")

    rt = built({**env, "PLAYWRIGHT_BROWSERS_PATH": "/elsewhere"})

    assert asked == [("chrome", {**env, "PLAYWRIGHT_BROWSERS_PATH": "/elsewhere"})]
    assert rt.browsers.pool.settings == rt.settings.browser
    assert (rt.settings.browser.channel, rt.settings.browser.max_tabs) == ("chrome", 2)


class Up:
    """A pool that says whose browser is up and keeps what it was asked to stop."""

    def __init__(self, *running: str) -> None:
        self.up, self.stopped, self.left = set(running), [], Counter()

    def running(self, agent_id: str) -> object | None:
        return object() if agent_id in self.up else None

    async def stop(self, agent_id: str) -> bool:
        self.stopped.append(agent_id)
        was = agent_id in self.up
        self.up.discard(agent_id)
        return was


def test_status_names_the_agents_whose_browser_is_up_in_order(tmp_path: Path):
    own = BrowserSettings(enabled=True, channel="chrome")
    browsers = Browsers(tmp_path, own, HERE, Up("ledger", "coach"))

    assert browsers.status(["default", "ledger", "coach", "gone"]) == {
        "enabled": True,
        # The channel the machine's file names, which is what a person reads the version of.
        "channel": "chrome",
        "installed": True,
        "version": HERE.version,
        "missing": "",
        "install_command": "",
        "running": ["coach", "ledger"],
    }


async def test_stopping_says_whether_there_was_one_and_is_nothing_without_a_pool(tmp_path: Path):
    pool = Up("coach")
    browsers = Browsers(tmp_path, BrowserSettings(enabled=True), HERE, pool)

    assert await browsers.stop("coach") is True
    assert await browsers.stop("coach") is False
    assert pool.stopped == ["coach", "coach"]
    assert await Browsers(tmp_path, BrowserSettings(), HERE).stop("coach") is False


async def test_a_removed_agent_takes_its_logins_with_it_and_nobody_elses(tmp_path: Path, caplog):
    root, pool = tmp_path / "browser", Up("coach")
    for agent_id in ("coach", "ledger"):
        (root / agent_id / "Default").mkdir(parents=True)
        (root / agent_id / "Default" / "Cookies").write_text("x", encoding="utf-8")
    browsers = Browsers(root, BrowserSettings(enabled=True), HERE, pool)
    gone = profile_dir(root, "coach")
    order: list[tuple[str, bool]] = []
    stop = pool.stop

    async def stop_first(agent_id: str) -> bool:
        order.append((agent_id, gone.exists()))
        return await stop(agent_id)

    pool.stop = stop_first

    with caplog.at_level(logging.WARNING, logger=LOG):
        await browsers.forget("coach")
        await browsers.forget("never-opened-a-page")

    # An agent that never opened a page has no folder to lose, which is nothing to warn of.
    assert told_by(caplog, LOG) == []
    # Stopped while its folder was still there: a browser writes to it as it closes.
    assert order == [("coach", True), ("never-opened-a-page", False)]
    assert not gone.exists()
    assert (root / "ledger" / "Default" / "Cookies").read_text(encoding="utf-8") == "x"
    # With the machine's browser turned off since, what was signed in to still goes.
    await Browsers(root, BrowserSettings(), HERE).forget("ledger")
    assert sorted(path.name for path in root.iterdir()) == []


@pytest.mark.parametrize("agent_id", ["", ".", "..", "../home", "coach/Default", "/tmp"])
async def test_an_id_that_is_not_one_plain_name_removes_nothing(tmp_path: Path, agent_id: str):
    root, pool = tmp_path / "home" / "browser", Up()
    (root / "coach" / "Default").mkdir(parents=True)
    (tmp_path / "home" / "agent.yaml").write_text("name: x\n", encoding="utf-8")
    browsers = Browsers(root, BrowserSettings(enabled=True), HERE, pool)

    with pytest.raises(ValueError, match="not an agent id"):
        await browsers.forget(agent_id)

    assert pool.stopped == []
    assert (root / "coach" / "Default").is_dir()
    assert (tmp_path / "home" / "agent.yaml").is_file()


async def test_a_folder_that_will_not_go_is_a_warning_and_not_a_failed_removal(
    tmp_path: Path, monkeypatch, caplog
):
    root = tmp_path / "browser"
    (root / "coach").mkdir(parents=True)

    def held(path, *args, **kwargs):
        raise PermissionError(13, "in use", str(path))

    monkeypatch.setattr(shutil, "rmtree", held)

    with caplog.at_level(logging.WARNING, logger=LOG):
        await Browsers(root, BrowserSettings(), HERE).forget("coach")

    ((level, told),) = told_by(caplog, LOG)
    assert level == "WARNING"
    assert told.startswith("browser profile of removed agent coach stays: ") and "in use" in told


class Rounds:
    """A pool whose rounds of reaping are scripted: a list of agents it stopped, or an error."""

    def __init__(self, *rounds: list[str] | Exception) -> None:
        self.rounds, self.asked, self.all_stopped = list(rounds), 0, 0
        self.shut, self.shut_when_stopped = False, False
        self.done = asyncio.Event()

    def running(self, agent_id: str) -> None:
        return None

    async def reap(self) -> list[str]:
        self.asked += 1
        if not self.rounds:
            self.done.set()
            return []
        answer = self.rounds.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    async def stop_all(self) -> None:
        self.all_stopped += 1
        self.shut_when_stopped = self.shut


async def test_the_reaper_goes_round_until_cancelled_and_a_failed_round_does_not_end_it(caplog):
    pool = Rounds(["coach"], RuntimeError("browser died"), ["ledger", "pong"])

    with caplog.at_level(logging.INFO, logger=LOG):
        loop = asyncio.ensure_future(reap_loop(pool, 0.001))
        await asyncio.wait_for(pool.done.wait(), 5)
        loop.cancel()
        with pytest.raises(asyncio.CancelledError):
            await loop

    assert told_by(caplog, LOG) == [
        ("INFO", "browser of agent coach stopped: nobody used it"),
        ("ERROR", "browser reap failed"),
        ("INFO", "browser of agent ledger stopped: nobody used it"),
        ("INFO", "browser of agent pong stopped: nobody used it"),
    ]
    assert pool.asked >= 4


async def test_the_reaper_waits_a_whole_interval_before_its_first_round():
    pool = Rounds()

    loop = asyncio.ensure_future(reap_loop(pool, 30))
    await asyncio.sleep(0.05)
    loop.cancel()

    assert pool.asked == 0
    assert browser_runtime.REAP_SECONDS == 60.0


@pytest.mark.parametrize("schedule", [False, True])
async def test_a_served_crew_reaps_while_it_is_up_and_stops_every_browser_as_it_goes_down(
    tmp_path: Path, machine, monkeypatch, schedule: bool
):
    pools: list[Rounds] = []

    def make(root: Path, settings: BrowserSettings) -> Rounds:
        pools.append(Rounds())
        return pools[-1]

    monkeypatch.setattr(browser_runtime, "BrowserPool", make)
    app_module = importlib.import_module("my_agent_crew.server.app")
    monkeypatch.setattr(app_module, "reap_loop", lambda pool: reap_loop(pool, 0.001))
    rt = built(crew(tmp_path))
    (pool,) = pools
    order: list[str] = []

    def noted(name: str, stop):
        async def stopped() -> None:
            await stop()
            order.append(name)

        return stopped

    monkeypatch.setattr(rt.drain, "stop", noted("turns", rt.drain.stop))
    monkeypatch.setattr(rt.scheduler, "stop", noted("jobs", rt.scheduler.stop))
    monkeypatch.setattr(pool, "stop_all", noted("browsers", pool.stop_all))
    app = create_app(rt, schedule=schedule)

    async with app.router.lifespan_context(app):
        await asyncio.wait_for(pool.done.wait(), 5)
        assert pool.all_stopped == 0 and pool.shut is False

    assert pool.all_stopped == 1
    # Marked before the stop: a call that lands while browsers close starts none.
    assert pool.shut_when_stopped is True
    # Browsers last: a turn or a job still running then would start one that nobody stops.
    assert order == ["turns", "jobs", "browsers"]
    asked = pool.asked
    await asyncio.sleep(0.05)
    assert pool.asked == asked  # and the loop went with the server


async def test_a_crew_without_a_browser_serves_and_goes_down_with_nothing_to_stop(
    tmp_path: Path, machine
):
    app = create_app(built(crew(tmp_path, config="")), schedule=False)

    async with app.router.lifespan_context(app):
        assert app.state.runtime.browsers.pool is None
