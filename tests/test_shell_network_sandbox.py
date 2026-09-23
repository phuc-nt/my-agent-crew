"""`shell_network: false`: an agent whose data must not leave the machine runs every
`shell_run` command in an OS sandbox — no network, no helpers that act for it, and writes
only where its profile says — rather than behind a pattern list."""

from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path

import httpx
import pytest

from my_agent_crew import texts
from my_agent_crew.agents.profile_yaml import load_yaml_profiles, parse_profile
from my_agent_crew.config import load_settings
from my_agent_crew.server.tool_assembly import build_tools
from my_agent_crew.store import Store
from my_agent_crew.tools import shell, shell_sandbox
from my_agent_crew.tools.registry import ToolRegistry
from my_agent_crew.tools.shell import SANDBOX_EXEC, SHELL_TOOL_NAME, build_shell_tool

needs_sandbox = pytest.mark.skipif(not SANDBOX_EXEC.is_file(), reason="macOS sandbox-exec only")


def python(code: str) -> str:
    return f'"{sys.executable}" -c "{code}"'


def connect_command(port: int) -> str:
    """A command that exits 0 only if it reached the listener on `port`."""
    return python(
        f"import socket; socket.create_connection(('127.0.0.1', {port}), timeout=3);"
        " print('reached')"
    )


async def listen() -> asyncio.Server:
    return await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)


async def run(tool_dir: Path, command: str, **kwargs):
    reg = ToolRegistry([build_shell_tool(tool_dir, **kwargs)])
    return await reg.execute(SHELL_TOOL_NAME, {"command": command})


@needs_sandbox
async def test_an_offline_command_cannot_open_a_connection(tmp_path: Path):
    """Localhost included: the crew's own API is one hop from every agent with a network."""
    server = await listen()
    port = server.sockets[0].getsockname()[1]
    try:
        online = await run(tmp_path, connect_command(port))
        offline = await run(tmp_path, connect_command(port), network=False)
    finally:
        server.close()
        await server.wait_closed()
    assert online.ok and "reached" in online.output
    # The sandbox's refusal, not a closed port's: that would be ConnectionRefusedError.
    assert offline.ok is False and "PermissionError" in offline.output


@needs_sandbox
async def test_an_offline_command_cannot_resolve_a_host_name(tmp_path: Path):
    """A lookup of a made-up name carries data out through the resolver without a single
    IP connection from the command, so DNS has to be closed too."""
    try:
        socket.gethostbyname("example.org")
    except OSError:
        pytest.skip("no DNS on this machine, so a failed lookup would prove nothing")
    lookup = python("import socket; print(socket.gethostbyname('example.org'))")
    assert (await run(tmp_path, lookup)).ok
    offline = await run(tmp_path, lookup, network=False)
    assert offline.ok is False and "gaierror" in offline.output


@needs_sandbox
async def test_an_offline_command_cannot_listen(tmp_path: Path):
    """A server left behind outlives the command and hands out files to whoever asks."""
    bind = python("import socket; socket.socket().bind(('127.0.0.1', 0)); print('bound')")
    assert (await run(tmp_path, bind)).ok
    offline = await run(tmp_path, bind, network=False)
    assert offline.ok is False and "PermissionError" in offline.output


@needs_sandbox
@pytest.mark.parametrize(
    "command",
    # Both fail harmlessly if the sandbox let them through: no such file, just the help.
    ["/usr/bin/open /no/such/file", "/bin/launchctl help"],
)
async def test_an_offline_command_cannot_ask_an_unsandboxed_helper(tmp_path: Path, command):
    """`open <url>` gets the browser, which is not sandboxed, to make the request."""
    result = await run(tmp_path, command, network=False)
    assert result.ok is False and "Operation not permitted" in result.output


@needs_sandbox
async def test_an_offline_command_writes_only_where_its_profile_says(tmp_path: Path, monkeypatch):
    """A write elsewhere is a delayed command: a script a scheduled job runs with the
    network, a git hook, a shell rc file. pytest's tmp_path sits in the temp directory,
    which the sandbox leaves writable, so the test takes that allowance away."""
    monkeypatch.setattr(shell_sandbox, "temp_dirs", lambda: ())
    workspace = tmp_path / "ledger"
    (workspace / "data").mkdir(parents=True)
    (workspace / "scripts").mkdir()
    (workspace / "scripts" / "fetch.py").write_text("print('fetch')\n", encoding="utf-8")
    (workspace / "data" / "fetch.py").symlink_to(workspace / "scripts" / "fetch.py")
    kwargs = {"network": False, "write_paths": [workspace / "data"]}

    ok = await run(workspace, "printf 'mot dong' > data/note.txt && cat data/note.txt", **kwargs)
    assert ok.ok and ok.output == "mot dong"
    for command in (
        "echo exfil >> scripts/fetch.py",
        "echo exfil >> data/fetch.py",  # through the symlink
        "mv scripts/fetch.py data/moved.py",
        f"echo exfil > {tmp_path / 'outside.txt'}",
    ):
        result = await run(workspace, command, **kwargs)
        assert result.ok is False and "Operation not permitted" in result.output, command
    assert (workspace / "scripts" / "fetch.py").read_text(encoding="utf-8") == "print('fetch')\n"
    assert not (tmp_path / "outside.txt").exists()


@needs_sandbox
async def test_an_offline_command_may_use_the_temp_directory(tmp_path: Path):
    result = await run(tmp_path, 'd=$(mktemp -d) && echo x > "$d/f" && cat "$d/f"', network=False)
    assert result.ok and result.output.strip() == "x"


async def test_without_sandbox_exec_an_offline_command_is_refused_not_run(
    tmp_path: Path, monkeypatch
):
    """Falling back to an unconfined run would be the one failure nobody notices."""
    monkeypatch.setattr(shell, "SANDBOX_EXEC", tmp_path / "no-sandbox-exec")
    result = await run(tmp_path, "touch ran.txt", network=False)
    assert result.ok is False and texts.SHELL_NO_SANDBOX in result.output
    assert not (tmp_path / "ran.txt").exists()


def write_agent(home: Path, body: str) -> None:
    (home / "agents" / "keeper").mkdir(parents=True)
    (home / "agents" / "keeper" / "agent.yaml").write_text(body, encoding="utf-8")


def test_the_network_stays_on_unless_a_profile_turns_it_off(tmp_path: Path):
    write_agent(tmp_path, "name: Keeper\nshell_network: false\nshell_write_paths: [data]\n")
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path)})
    profiles = {p.id: p for p in load_yaml_profiles(settings)}
    keeper = profiles["keeper"]
    assert keeper.settings.shell_network is False
    assert keeper.shell_write_dirs == ((keeper.workspace / "data").resolve(),)
    assert keeper.to_dict()["shell_network"] is False
    assert keeper.to_dict()["shell_write_paths"] == ["data"]
    assert profiles["default"].settings.shell_network is True


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        # Read as truthy, this would leave the network open on the agent meant to close it.
        ({"shell_network": "false"}, "shell_network"),
        ({"shell_write_paths": ["../../.."]}, "leaves the workspace"),
        ({"shell_write_paths": "data"}, "shell_write_paths"),
    ],
)
def test_a_profile_that_would_weaken_the_sandbox_is_refused(tmp_path: Path, raw, message):
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path)})
    with pytest.raises(ValueError, match=message):
        parse_profile("keeper", tmp_path / "agents" / "keeper", raw, settings)


@needs_sandbox
async def test_the_assembled_shell_tool_of_an_offline_agent_is_sandboxed(tmp_path: Path):
    """The setting only matters if it reaches the tool the agent is actually given."""
    write_agent(tmp_path, "name: Keeper\nshell_network: false\nworkspace: work\n")
    (tmp_path / "agents" / "keeper" / "work").mkdir()
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path)})
    keeper = next(p for p in load_yaml_profiles(settings) if p.id == "keeper")
    server = await listen()
    port = server.sockets[0].getsockname()[1]
    try:
        async with httpx.AsyncClient() as client:
            reg = build_tools(keeper, client, Store(":memory:"), skills=())
            result = await reg.execute(SHELL_TOOL_NAME, {"command": connect_command(port)})
    finally:
        server.close()
        await server.wait_closed()
    assert result.ok is False and "PermissionError" in result.output
