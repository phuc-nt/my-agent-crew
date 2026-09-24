"""An agent kept to its job inside someone's repo: it may fetch and record, but its shell
writes only under `shell_write_paths` (network on or off) and never runs a command matching
`shell_deny_patterns`. Each refusal tells the model to stop and report what it needed, so
the change reaches the person instead of a workaround."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import httpx
import pytest

from my_agent_crew import texts
from my_agent_crew.agent.events import ApprovalRequiredEvent, ToolResultEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agents.profile_edit import apply_patch
from my_agent_crew.agents.profile_yaml import load_yaml_profiles, parse_profile
from my_agent_crew.config import load_settings
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.server.tool_assembly import build_tools
from my_agent_crew.store import Store
from my_agent_crew.tools import shell_sandbox
from my_agent_crew.tools.registry import ToolRegistry
from my_agent_crew.tools.shell import SHELL_TOOL_NAME, build_shell_tool
from my_agent_crew.tools.shell_sandbox import sandbox_profile
from my_agent_crew.tools.workspace import build_workspace_tools
from tests.conftest import collect
from tests.test_shell_network_sandbox import connect_command, listen, needs_sandbox, run

BLOCKED = "Status: BLOCKED"


def repo(tmp_path: Path) -> Path:
    workspace = tmp_path / "coach"
    (workspace / "data").mkdir(parents=True)
    (workspace / "scripts").mkdir()
    (workspace / "scripts" / "sync.py").write_text("print('sync')\n", encoding="utf-8")
    return workspace


def test_the_profile_keeps_the_network_only_when_asked_and_the_helpers_denied_either_way():
    """`launchctl` or `osascript` would run an edit outside the sandbox for the command."""
    online = sandbox_profile([Path("/w/data")], network=True)
    offline = sandbox_profile([Path("/w/data")])
    assert "(deny network*)" not in online and "(deny network*)" in offline
    for profile in (online, offline):
        assert '(subpath "/w/data")' in profile and "/bin/launchctl" in profile


@needs_sandbox
async def test_write_paths_confine_a_networked_command_to_its_data(tmp_path: Path, monkeypatch):
    """pytest's tmp_path sits in the temp directory, which the sandbox leaves writable, so
    the test takes that allowance away."""
    monkeypatch.setattr(shell_sandbox, "temp_dirs", lambda: ())
    workspace = repo(tmp_path)
    kwargs = {"write_paths": [workspace / "data"]}
    server = await listen()
    port = server.sockets[0].getsockname()[1]
    try:
        reached = await run(workspace, connect_command(port), **kwargs)
    finally:
        server.close()
        await server.wait_closed()
    recorded = await run(workspace, "echo 1 > data/row.txt && cat data/row.txt", **kwargs)
    edited = await run(workspace, "echo hack >> scripts/sync.py", **kwargs)

    assert reached.ok and "reached" in reached.output
    assert recorded.ok and recorded.output.strip() == "1"
    assert edited.ok is False and "Operation not permitted" in edited.output
    assert str(workspace / "data") in edited.output and BLOCKED in edited.output
    assert (workspace / "scripts" / "sync.py").read_text(encoding="utf-8") == "print('sync')\n"


@needs_sandbox
async def test_without_write_paths_a_networked_command_is_not_sandboxed(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(shell_sandbox, "temp_dirs", lambda: ())
    workspace = repo(tmp_path)
    result = await run(workspace, "echo more >> scripts/sync.py")
    assert result.ok and "more" in (workspace / "scripts" / "sync.py").read_text(encoding="utf-8")


async def test_a_denied_command_is_refused_before_it_runs(tmp_path: Path):
    workspace = repo(tmp_path)
    result = await run(
        workspace,
        "sqlite3 data/x.db 'CREATE TABLE t(a)' && touch ran",
        deny_patterns=["create table"],
    )
    assert result.ok is False and '"create table"' in result.output and BLOCKED in result.output
    assert not (workspace / "ran").exists()
    assert (await run(workspace, "echo ok", deny_patterns=["create table"])).ok


async def test_a_denied_command_does_not_pause_for_an_approval_nobody_can_grant(deps_factory):
    """A supervised conversation would otherwise ask the person to approve a command the
    tool refuses anyway, and a delegated child would wait on nobody. `rm -rf` is on the
    default ask list too: the refusal wins over asking."""
    deps = deps_factory(
        script=[
            completion(tool_calls=(ToolCall("c1", SHELL_TOOL_NAME, {"command": "rm -rf data"}),)),
            completion("cần người dùng đồng ý"),
        ],
        shell_deny_patterns=("rm -rf",),
    )
    shell = build_shell_tool(deps.agent.workspace, deny_patterns=deps.settings.shell_deny_patterns)
    deps = dataclasses.replace(deps, tools=ToolRegistry([shell]))
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "dọn dữ liệu"))

    assert not any(isinstance(e, ApprovalRequiredEvent) for e in events)
    result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert result.ok is False and BLOCKED in result.output


async def test_a_workspace_write_outside_its_paths_says_to_report_back(tmp_path: Path):
    workspace = repo(tmp_path)
    reg = ToolRegistry(build_workspace_tools(workspace, ["data"]))
    result = await reg.execute("workspace_write", {"path": "scripts/new.py", "content": "x"})
    assert result.ok is False and BLOCKED in result.output


def write_coach(home: Path, body: str) -> None:
    (home / "agents" / "coach").mkdir(parents=True)
    (home / "agents" / "coach" / "agent.yaml").write_text(body, encoding="utf-8")


def test_deny_patterns_are_read_per_agent_and_must_be_a_list(tmp_path: Path):
    write_coach(tmp_path, "name: Coach\nshell_deny_patterns: [create table, ' python3 -c ']\n")
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path)})
    profiles = {p.id: p for p in load_yaml_profiles(settings)}
    coach = profiles["coach"]
    assert coach.settings.shell_deny_patterns == ("create table", "python3 -c")
    assert coach.to_dict()["shell_deny_patterns"] == ["create table", "python3 -c"]
    assert profiles["default"].settings.shell_deny_patterns == ()
    with pytest.raises(ValueError, match="shell_deny_patterns"):
        parse_profile(
            "coach", tmp_path / "agents" / "coach", {"shell_deny_patterns": "x"}, settings
        )
    with pytest.raises(ValueError):
        apply_patch({}, {"shell_deny_patterns": "drop table"})


@needs_sandbox
async def test_the_assembled_tool_of_a_networked_agent_is_confined(tmp_path: Path, monkeypatch):
    """The settings only matter if they reach the tool the agent is actually given."""
    monkeypatch.setattr(shell_sandbox, "temp_dirs", lambda: ())
    write_coach(
        tmp_path,
        "name: Coach\nworkspace: work\nshell_write_paths: [data]\n"
        "shell_deny_patterns: [drop table]\n",
    )
    workspace = tmp_path / "agents" / "coach" / "work"
    (workspace / "data").mkdir(parents=True)
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path)})
    coach = next(p for p in load_yaml_profiles(settings) if p.id == "coach")
    async with httpx.AsyncClient() as client:
        reg = build_tools(coach, client, Store(":memory:"), skills=())
        outside = await reg.execute(SHELL_TOOL_NAME, {"command": "touch README.md"})
        denied = await reg.execute(SHELL_TOOL_NAME, {"command": "echo DROP TABLE t"})
        inside = await reg.execute(SHELL_TOOL_NAME, {"command": "touch data/ok"})
    assert outside.ok is False and texts.REPORT_BACK in outside.output
    assert denied.ok is False and '"drop table"' in denied.output
    assert inside.ok and (workspace / "data" / "ok").exists()
