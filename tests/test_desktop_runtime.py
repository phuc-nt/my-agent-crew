"""The desktop as the server holds it: each agent given the tools its own `computer` key asks
for, with or without a helper on the machine, and the helper's socket closed to every file
tool and to every command in a sandbox."""

from __future__ import annotations

import asyncio
import logging
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from my_agent_crew import texts
from my_agent_crew import texts_desktop as t
from my_agent_crew.config import load_settings
from my_agent_crew.config_desktop import DesktopSettings
from my_agent_crew.desktop.kit import ACT, DESKTOP_TOOLS, OBSERVE, SCREENSHOT, STATE
from my_agent_crew.server.desktop_runtime import close_desktop, desktop_private
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.tools.private_paths import is_private
from my_agent_crew.tools.shell_sandbox import private_rules
from tests.browser_crew import built
from tests.browser_crew import crew_home as crew
from tests.desktop_helper import VERSION, FakeHelper, desk, frame, listening, socket_folder
from tests.test_private_paths import folds_case
from tests.test_shell_network_sandbox import needs_sandbox, python, run

ASSEMBLY = "my_agent_crew.server.tool_assembly"
SCRIPT = "tool_script"
ON = 'computer: "on"\n'
# What each tool is called with when all that is being asked is whether it reaches a helper.
CALLS = {
    STATE: {},
    SCREENSHOT: {},
    OBSERVE: {"app": "Notes"},
    ACT: {"kind": "click", "app": "Notes", "frame_id": frame(1), "x": 1, "y": 1},
}


def desktop_tools(rt: Runtime, agent_id: str) -> list[str]:
    return [name for name in rt.deps_for(agent_id).tools.names() if name.startswith("computer_")]


# What a listener says to whoever connects. A command that failed prints its own source in the
# traceback, so what proves a connection is a word the command does not hold.
GREETING = b"welcome to the socket"
CONNECT = "import json, socket; s = socket.socket(socket.AF_UNIX); "


def greeted(path: Path) -> str:
    """A command that prints what whoever listens at `path` says first."""
    return python(f"{CONNECT}s.connect('{path}'); print(s.recv(64).decode())")


def asking(path: Path) -> str:
    """A command that asks the helper at `path` for its state, as any program of the user
    could, and prints the answer."""
    line = "(json.dumps({'id': 'shell', 'cmd': 'state'}) + chr(10)).encode()"
    return python(f"{CONNECT}s.connect('{path}'); s.sendall({line}); print(s.recv(4096).decode())")


def test_each_agent_is_given_the_desktop_tools_its_own_key_asks_for(tmp_path: Path):
    env = crew(
        tmp_path,
        config="",
        plain="description: no key\n",
        off='computer: "off"\n',
        looker=ON,
        doer=ON + "computer_apps: [Notes]\n",
    )

    rt = built(env)

    for without in ("default", "plain", "off"):
        assert desktop_tools(rt, without) == [], without
    # With no application the agent still holds all four: the one that acts refuses each
    # call, which tells the agent why, where a missing tool would tell it nothing.
    assert desktop_tools(rt, "looker") == desktop_tools(rt, "doer") == list(DESKTOP_TOOLS)
    held = [rt.deps_for("doer").tools.get(name) for name in DESKTOP_TOOLS]
    assert [tool.name for tool in held if tool.requires_approval] == [ACT]
    # Each tells the owner's screens it follows the agent's `computer` key and no list.
    assert [tool.to_dict() for tool in held] == [
        {
            "name": tool.name,
            "description": tool.description,
            "requires_approval": tool.requires_approval,
            "with_desktop": True,
        }
        for tool in held
    ]
    assert not (tmp_path / "home" / "desktop").exists()


async def test_with_no_helper_on_the_machine_every_tool_is_there_and_says_there_is_none(
    tmp_path: Path,
):
    rt = built(crew(tmp_path, config="", doer=ON + "computer_apps: [Notes]\n"))
    held = rt.deps_for("doer").tools

    for name, args in CALLS.items():
        answer = await held.execute(name, args)

        assert not answer.ok and t.HELPER_ERRORS["absent"] in answer.output, name


def test_the_tools_list_neither_brings_a_desktop_tool_nor_takes_one_away(tmp_path: Path, caplog):
    env = crew(
        tmp_path,
        config="",
        narrow="tools: [workspace_read]\n" + ON,
        named=f"tools: [workspace_read, {ACT}]\n" + ON,
        bare=f"tools: [workspace_read, {STATE}]\n",
    )

    with caplog.at_level(logging.WARNING, logger=ASSEMBLY):
        rt = built(env)

    # `tool_script` comes to whoever holds a tool that reads, after everything else.
    for with_key in ("narrow", "named"):
        held = rt.deps_for(with_key).tools.names()
        assert held == ["workspace_read", *DESKTOP_TOOLS, SCRIPT], with_key
    assert rt.deps_for("bare").tools.names() == ["workspace_read", SCRIPT]
    # A list that names one is told what does bring it, whether or not the agent has it.
    told = sorted(r.getMessage() for r in caplog.records if r.name == ASSEMBLY)
    key = "the desktop tools come with the agent's `computer` key"
    assert len(told) == 2 and all(line.endswith(key) for line in told)
    assert told[0].startswith(f"agent bare: tools lists {STATE}, ")
    assert told[1].startswith(f"agent named: tools lists {ACT}, ")
    # And no list is offered one to tick: the key is the only switch.
    for agent_id in ("narrow", "named", "bare", "default"):
        offered = rt.deps_for(agent_id).listable_tools
        assert "workspace_read" in offered and not set(offered) & set(DESKTOP_TOOLS), agent_id


def test_what_is_closed_is_the_helpers_folder_and_a_socket_put_elsewhere(tmp_path: Path):
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path)})
    root = settings.home / "desktop"

    def closed(socket: str) -> tuple[Path, ...]:
        return desktop_private(replace(settings, desktop=DesktopSettings(socket=socket)))

    assert closed("") == (root,)
    assert closed(str(root / "deep" / "sock")) == (root,)
    # The folder a socket elsewhere is in is not closed with it: it may be one many share.
    assert closed("/tmp/dh-elsewhere/sock") == (root, Path("/tmp/dh-elsewhere/sock"))
    assert closed(str(settings.home / "desktops" / "sock"))[1:] == (
        settings.home / "desktops" / "sock",
    )

    close_desktop(replace(settings, desktop=DesktopSettings(socket="/tmp/dh-elsewhere/sock")))

    assert is_private(root) and is_private(root / "sock") and is_private(root / "a" / "b")
    assert is_private(Path("/tmp/dh-elsewhere/sock"))
    assert not is_private(Path("/tmp/dh-elsewhere")) and not is_private(Path("/tmp/dh-elsewhere/x"))
    assert not is_private(settings.home) and not is_private(settings.home / "desktops")


def test_a_socket_that_climbs_out_of_the_helpers_folder_is_closed_where_it_leads(
    tmp_path: Path,
):
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path)})
    root, climbed = settings.home / "desktop", str(settings.home / "desktop/../other/sock")
    moved = replace(settings, desktop=DesktopSettings(socket=climbed))

    assert desktop_private(moved) == (root, Path(climbed))

    close_desktop(moved)

    assert is_private(settings.home / "other" / "sock") and is_private(root)
    assert not is_private(settings.home / "other" / "note.md")


@pytest.mark.parametrize("own", ["description: x\n", ON], ids=["nobody uses it", "one agent does"])
async def test_the_folder_is_closed_to_the_file_tools_whoever_uses_the_desktop(
    tmp_path: Path, own: str
):
    home = tmp_path / "home"
    env = crew(tmp_path, config="", coach=own, wide=f"workspace: {home}\n")
    (home / "desktop").mkdir()
    (home / "desktop" / "note.md").write_text("khoa bimat\n", encoding="utf-8")
    (home / "inbox").mkdir()
    (home / "inbox" / "note.md").write_text("thu cua chu\n", encoding="utf-8")

    rt = built(env)
    # Where the disk folds case, as macOS does, another spelling is the same folder.
    spelt = "DESKTOP" if folds_case(tmp_path) else "desktop"

    assert is_private(home / "desktop" / "sock") and not is_private(home / "inbox" / "note.md")
    # An agent whose workspace is the crew home itself walks everything else in it.
    wide = rt.deps_for("wide").tools
    read = await wide.execute("workspace_read", {"path": "inbox/note.md"})
    assert read.ok and "thu cua chu" in read.output
    for name, args in (
        ("workspace_list", {"path": "desktop"}),
        ("workspace_read", {"path": "desktop/note.md"}),
        ("workspace_read", {"path": "desktop/sock"}),
        ("workspace_write", {"path": "desktop/sock", "content": "x"}),
        ("workspace_write", {"path": f"{spelt}/new.md", "content": "x"}),
    ):
        answer = await wide.execute(name, args)

        assert not answer.ok and texts.WORKSPACE_PRIVATE in answer.output, (name, args)
        assert "bimat" not in answer.output, (name, args)
    assert sorted(found.name for found in (home / "desktop").iterdir()) == ["note.md"]


def test_a_runtime_made_around_a_few_agents_closes_the_folder_too(deps_factory):
    deps = deps_factory()

    Runtime.single(deps)

    assert is_private(deps.settings.home / "desktop" / "sock")
    assert not is_private(deps.settings.home / "inbox")


async def test_an_agent_that_works_in_the_crew_home_keeps_no_picture_beside_the_socket(
    tmp_path: Path,
):
    home = tmp_path / "home"
    async with listening(apps=desk(), front="Notes") as helper:
        config = f"desktop_socket: {helper.path}\n"
        rt = built(crew(tmp_path, config=config, wide=f"workspace: {home}\n" + ON))

        answer = await rt.deps_for("wide").tools.execute(SCREENSHOT, {})

        # Its pictures would lie in the folder the helper keeps its socket in, which no
        # file tool writes into: none is taken, rather than one put somewhere else.
        assert not answer.ok and texts.WORKSPACE_PRIVATE in answer.output
        assert helper.requests == [] and not (home / "desktop").exists()


def test_the_rules_close_a_private_folder_to_a_connection_as_well():
    rules = private_rules([Path("/h/desktop")])

    assert rules.startswith('(deny file-read* file-write* network-outbound (subpath "/h/desktop"))')


async def greet(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    writer.write(GREETING)
    await writer.drain()
    writer.close()


@needs_sandbox
@pytest.mark.parametrize("named", ["the folder", "the socket"])
async def test_no_command_in_a_sandbox_connects_to_a_socket_kept_private(
    tmp_path: Path, named: str
):
    """With the network on too: a Unix socket is reached by `connect`, which the rules that
    close a folder's files do not judge."""
    folder = socket_folder().resolve()
    kept, beside = folder / "kept" / "sock", folder / "beside" / "sock"
    private = [kept.parent if named == "the folder" else kept]
    servers = []
    try:
        for path in (kept, beside):
            path.parent.mkdir()
            servers.append(await asyncio.start_unix_server(greet, path=str(path)))
        online = await run(tmp_path, greeted(kept), write_paths=[tmp_path], private=private)
        offline = await run(tmp_path, greeted(kept), network=False, private=private)
        near = await run(tmp_path, greeted(beside), write_paths=[tmp_path], private=private)
        free = await run(tmp_path, greeted(kept), private=private)
    finally:
        for server in servers:
            server.close()
            await server.wait_closed()
        shutil.rmtree(folder, ignore_errors=True)

    said = GREETING.decode()
    for refused in (online, offline):
        assert not refused.ok and "PermissionError" in refused.output
        assert said not in refused.output
    # What lies beside it is reached as before, and a shell nothing confines is not confined
    # by this either: the helper answers whoever its user runs.
    assert near.ok and said in near.output
    assert free.ok and said in free.output


@needs_sandbox
@pytest.mark.parametrize("elsewhere", [False, True], ids=["under the home", "put elsewhere"])
async def test_a_confined_shell_does_not_reach_the_helper_the_tools_talk_to(elsewhere: bool):
    """The crew as it runs: the tools find the helper at its socket, an agent whose shell is
    confined cannot connect to it, and one whose shell runs free can, which is the stated
    limit and why such an agent's every command is the gate's."""
    root = socket_folder()
    folder = root / "kept" if elsewhere else root / "home" / "desktop"
    config = f"desktop_socket: {folder / 'sock'}\n" if elsewhere else ""
    env = crew(root, config=config, closed="shell_write_paths: ['.']\n" + ON, open=ON)
    folder.mkdir()
    helper = FakeHelper(folder, apps=desk(), front="Notes")
    try:
        await helper.start()
        rt = built(env)
        answers = {}
        for agent_id in ("closed", "open"):
            held = rt.deps_for(agent_id).tools
            state = await held.execute(STATE, {})
            assert state.ok and VERSION in state.output, agent_id
            answers[agent_id] = await held.execute("shell_run", {"command": asking(helper.path)})
    finally:
        await helper.stop()
        shutil.rmtree(root, ignore_errors=True)

    refused, reached = answers["closed"], answers["open"]
    assert not refused.ok and "PermissionError" in refused.output
    assert "cổng của trình trợ giúp desktop" in refused.output
    assert '"ok": true' not in refused.output
    assert reached.ok and '"ok": true' in reached.output and VERSION in reached.output
    # Each agent's tool looked twice; of the two commands only the free one was heard.
    heard = [(request["cmd"], request["id"] == "shell") for request in helper.requests]
    assert heard == [("state", False), ("apps", False)] * 2 + [("state", True)]
