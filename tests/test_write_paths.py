"""`write_paths`: where the file tools may write inside a workspace. An autonomous agent never
stops for approval, so this is the only thing between a guessed path in its task and a new
folder of personal data in a git repo."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from my_agent_crew import texts
from my_agent_crew.agents.profile_edit import apply_patch
from my_agent_crew.agents.profile_yaml import load_yaml_profiles, parse_profile
from my_agent_crew.config import load_settings
from my_agent_crew.server.tool_assembly import build_tools
from my_agent_crew.store import Store
from my_agent_crew.tools.registry import ToolRegistry
from my_agent_crew.tools.workspace import build_workspace_tools
from my_agent_crew.tools.workspace_edit import build_edit_tool


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    (tmp_path / "README.md").write_text("repo\n", encoding="utf-8")
    return tmp_path


async def test_a_write_under_a_listed_path_lands(repo: Path):
    reg = ToolRegistry(build_workspace_tools(repo, ("data",)))
    result = await reg.execute("workspace_write", {"path": "data/charts/a.md", "content": "x"})
    assert result.ok and (repo / "data" / "charts" / "a.md").read_text() == "x"


@pytest.mark.parametrize("path", ["2026/boxing.md", "journal/2026-09-24.md", "notes.md"])
async def test_a_write_elsewhere_is_refused_and_creates_nothing(repo: Path, path: str):
    reg = ToolRegistry(build_workspace_tools(repo, ("data",)))
    result = await reg.execute("workspace_write", {"path": path, "content": "rpe 4"})

    assert not result.ok and "data" in result.output
    assert sorted(p.name for p in repo.iterdir()) == ["README.md", "data"]


async def test_walking_out_of_a_listed_path_is_still_outside_it(repo: Path):
    reg = ToolRegistry(build_workspace_tools(repo, ("data",)))
    result = await reg.execute("workspace_write", {"path": "data/../notes.md", "content": "x"})
    assert not result.ok and not (repo / "notes.md").exists()


async def test_without_write_paths_the_whole_workspace_stays_writable(repo: Path):
    reg = ToolRegistry(build_workspace_tools(repo))
    result = await reg.execute("workspace_write", {"path": "notes/a.md", "content": "x"})
    assert result.ok and (repo / "notes" / "a.md").exists()


async def test_an_edit_outside_the_listed_paths_is_refused(repo: Path):
    reg = ToolRegistry([build_edit_tool(repo, ("data",))])
    result = await reg.execute(
        "workspace_edit", {"path": "README.md", "old": "repo", "new": "rpe 4"}
    )
    assert not result.ok and (repo / "README.md").read_text() == "repo\n"


def _write_agent(home: Path, body: str) -> None:
    (home / "agents" / "coach").mkdir(parents=True)
    (home / "agents" / "coach" / "agent.yaml").write_text(body, encoding="utf-8")


async def test_the_assembled_tools_of_an_agent_obey_its_profile(tmp_path: Path, store: Store):
    _write_agent(tmp_path, "name: Coach\nworkspace: repo\nwrite_paths: [data]\n")
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path)})
    coach = {p.id: p for p in load_yaml_profiles(settings)}["coach"]
    assert coach.to_dict()["write_paths"] == ["data"]
    coach.workspace.mkdir(parents=True)

    async with httpx.AsyncClient() as client:
        reg = build_tools(coach, client, store, [])
    refused = await reg.execute("workspace_write", {"path": "2026/boxing.md", "content": "x"})
    landed = await reg.execute("workspace_write", {"path": "data/a.md", "content": "x"})

    assert not refused.ok and texts.WORKSPACE_WRITE_OUTSIDE.split("{")[0] in refused.output
    assert landed.ok and (coach.workspace / "data" / "a.md").exists()


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ({"write_paths": ["../.."]}, "leaves the workspace"),
        ({"write_paths": "data"}, "write_paths"),
    ],
)
def test_a_profile_with_a_bad_write_path_is_refused(tmp_path: Path, raw, message):
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path)})
    with pytest.raises(ValueError, match=message):
        parse_profile("coach", tmp_path / "agents" / "coach", raw, settings)


def test_the_profile_editor_refuses_a_bare_string_for_write_paths():
    with pytest.raises(ValueError, match="write_paths"):
        apply_patch({}, {"write_paths": "data"})
