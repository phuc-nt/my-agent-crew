"""`shell_network: false`: an agent whose data must not leave the machine runs every
`shell_run` command with outbound connections denied by the OS, not by a pattern list."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx
import pytest

from my_agent_crew import texts
from my_agent_crew.agents.profile_yaml import load_yaml_profiles, parse_profile
from my_agent_crew.config import load_settings
from my_agent_crew.server.tool_assembly import build_tools
from my_agent_crew.store import Store
from my_agent_crew.tools import shell
from my_agent_crew.tools.registry import ToolRegistry
from my_agent_crew.tools.shell import SANDBOX_EXEC, SHELL_TOOL_NAME, build_shell_tool

needs_sandbox = pytest.mark.skipif(not SANDBOX_EXEC.is_file(), reason="macOS sandbox-exec only")


def connect_command(port: int) -> str:
    """A command that exits 0 only if it reached the listener on `port`."""
    code = (
        f"import socket; socket.create_connection(('127.0.0.1', {port}), timeout=3);"
        " print('reached')"
    )
    return f'"{sys.executable}" -c "{code}"'


async def listen() -> asyncio.Server:
    return await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)


@needs_sandbox
async def test_an_offline_command_cannot_open_a_connection(tmp_path: Path):
    """Localhost included: the crew's own API is one hop from every agent with a network."""
    server = await listen()
    port = server.sockets[0].getsockname()[1]
    try:
        online = await ToolRegistry([build_shell_tool(tmp_path)]).execute(
            SHELL_TOOL_NAME, {"command": connect_command(port)}
        )
        offline = await ToolRegistry([build_shell_tool(tmp_path, network=False)]).execute(
            SHELL_TOOL_NAME, {"command": connect_command(port)}
        )
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
    code = "import socket; print(socket.gethostbyname('localhost.example.org'))"
    reg = ToolRegistry([build_shell_tool(tmp_path, network=False)])
    result = await reg.execute(SHELL_TOOL_NAME, {"command": f'"{sys.executable}" -c "{code}"'})
    assert result.ok is False and "gaierror" in result.output


@needs_sandbox
async def test_an_offline_command_still_reads_and_writes_its_workspace(tmp_path: Path):
    (tmp_path / "so-cai.txt").write_text("một dòng\n", encoding="utf-8")
    reg = ToolRegistry([build_shell_tool(tmp_path, network=False)])
    result = await reg.execute(
        SHELL_TOOL_NAME, {"command": "cat so-cai.txt > ban-sao.txt && wc -l < ban-sao.txt"}
    )
    assert result.ok and result.output.strip() == "1"
    assert (tmp_path / "ban-sao.txt").read_text(encoding="utf-8") == "một dòng\n"


async def test_without_sandbox_exec_an_offline_command_is_refused_not_run(
    tmp_path: Path, monkeypatch
):
    """Falling back to an unconfined run would be the one failure nobody notices."""
    monkeypatch.setattr(shell, "SANDBOX_EXEC", tmp_path / "no-sandbox-exec")
    reg = ToolRegistry([build_shell_tool(tmp_path, network=False)])
    result = await reg.execute(SHELL_TOOL_NAME, {"command": "touch ran.txt"})
    assert result.ok is False and texts.SHELL_NO_SANDBOX in result.output
    assert not (tmp_path / "ran.txt").exists()


def write_agent(home: Path, body: str) -> None:
    (home / "agents" / "keeper").mkdir(parents=True)
    (home / "agents" / "keeper" / "agent.yaml").write_text(body, encoding="utf-8")


def test_the_network_stays_on_unless_a_profile_turns_it_off(tmp_path: Path):
    write_agent(tmp_path, "name: Keeper\nshell_network: false\n")
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path)})
    profiles = {p.id: p for p in load_yaml_profiles(settings)}
    assert profiles["keeper"].settings.shell_network is False
    assert profiles["keeper"].to_dict()["shell_network"] is False
    assert profiles["default"].settings.shell_network is True


def test_a_quoted_false_is_refused_rather_than_read_as_true(tmp_path: Path):
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path)})
    with pytest.raises(ValueError, match="shell_network"):
        parse_profile("keeper", tmp_path, {"shell_network": "false"}, settings)


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
