"""Harness kits (`.agents/`, `.claude/`, `.opencode/`): what each scope contributes, and
how an agent written as markdown becomes a crew member."""

from __future__ import annotations

import json
from pathlib import Path

from my_agent_crew.agents import load_profiles
from my_agent_crew.agents.context import bootstrap_sections
from my_agent_crew.agents.kit import (
    AGENT,
    HOME,
    Kit,
    agent_kits,
    discover_kits,
    split_front_matter,
)
from my_agent_crew.agents.kit_agents import parse_agent_md, tool_names
from my_agent_crew.config import Settings

REVIEWER_MD = """---
name: Reviewer
description: Reviews code.   Never edits.
model: sonnet
tools: Read, Grep, Bash, NotebookEdit
---
You review code and report findings.
"""

CODER_MD = """---
name: Coder
description: Writes code.
model: openrouter:x/y, openrouter:z/w
tools:
  - Read
  - Edit
  - Task
delegates: [reviewer]
workspace: src
---
You write code.
"""


def kit_tree(
    root: Path, agents: dict[str, str] | None = None, commands: dict[str, str] | None = None
) -> Path:
    """`root` is the kit directory itself: `<project>/.agents`, `.claude` or `.opencode`."""
    root.mkdir(parents=True, exist_ok=True)
    for name, text in (agents or {}).items():
        (root / "agents").mkdir(exist_ok=True)
        (root / "agents" / f"{name}.md").write_text(text)
    for name, text in (commands or {}).items():
        path = root / "commands" / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def test_split_front_matter_handles_plain_and_fenced_text():
    assert split_front_matter("hello") == ({}, "hello")
    assert split_front_matter("---\nname: A\n---\nbody\n") == ({"name": "A"}, "body")
    assert split_front_matter("--- not really\ntext") == ({}, "--- not really\ntext")


def test_discover_kits_finds_every_harness_dir_in_order(tmp_path: Path):
    for name in (".opencode", ".claude", ".agents", ".other"):
        (tmp_path / name).mkdir()
    kits = discover_kits(tmp_path, tmp_path, AGENT)
    assert [k.root.name for k in kits] == [".agents", ".claude", ".opencode"]
    assert all(k.project == tmp_path and k.scope == AGENT for k in kits)


def test_kit_lists_skills_agents_and_namespaced_commands(tmp_path: Path):
    root = kit_tree(
        tmp_path / ".claude",
        agents={"b": REVIEWER_MD, "a": CODER_MD},
        commands={"review": "x", "mk/plan": "y"},
    )
    (root / "skills" / "s").mkdir(parents=True)
    (root / "settings.json").write_text("{}")
    kit = Kit(root, tmp_path)
    assert [p.stem for p in kit.agent_files] == ["a", "b"]
    assert [kit.command_name(p) for p in kit.command_files] == ["mk:plan", "review"]
    assert kit.skills_dirs == (root / "skills",)
    assert kit.settings_file == root / "settings.json"
    assert kit.scope == HOME


def test_tool_names_maps_harness_aliases_and_keeps_implicit_tools():
    names = tool_names("Read, Grep, Bash, NotebookEdit, skill_read")
    assert names[:3] == ["workspace_read", "workspace_grep", "shell_run"]
    assert "NotebookEdit" not in names and names.count("skill_read") == 1
    assert {"memory_save", "image_read"} <= set(names)
    assert tool_names(None) == [] and tool_names(["Edit", "MultiEdit"])[:1] == ["workspace_edit"]


def test_parse_agent_md_builds_a_profile_from_front_matter(settings: Settings, tmp_path: Path):
    agents = {"reviewer": REVIEWER_MD, "coder": CODER_MD}
    root = kit_tree(tmp_path / "proj" / ".claude", agents=agents)
    kit = Kit(root, tmp_path / "ws", AGENT)
    reviewer = parse_agent_md(root / "agents" / "reviewer.md", kit, settings)
    assert reviewer.id == "reviewer" and reviewer.name == "Reviewer"
    assert reviewer.description == "Reviews code. Never edits."
    assert reviewer.dir == settings.home / "agents" / "reviewer"
    assert reviewer.workspace == (tmp_path / "ws").resolve()
    assert reviewer.mode == "assistant" and reviewer.settings.routes == settings.routes
    assert reviewer.persona_files == (str(root / "agents" / "reviewer.md"),)
    coder = parse_agent_md(root / "agents" / "coder.md", kit, settings)
    assert coder.mode == "work" and coder.delegates == ("reviewer",)
    routes = [f"{r.provider}:{r.model}" for r in coder.settings.routes]
    assert routes == ["openrouter:x/y", "openrouter:z/w"]
    assert coder.workspace == (tmp_path / "proj" / "src").resolve()
    assert coder.tools[:3] == ("workspace_read", "workspace_edit", "delegate")


def test_persona_section_drops_the_front_matter_and_names_the_file(settings: Settings):
    root = kit_tree(settings.home / ".agents", agents={"reviewer": REVIEWER_MD})
    kit = Kit(root, settings.workspace_dir, HOME)
    profile = parse_agent_md(root / "agents" / "reviewer.md", kit, settings)
    [(title, body)] = [s for s in bootstrap_sections(profile) if s[0] == "reviewer.md"]
    assert body == "You review code and report findings."
    assert profile.to_dict()["persona_files"] == [str(root / "agents" / "reviewer.md")]


def test_load_profiles_adds_home_kit_agents_and_lets_yaml_win(settings: Settings):
    home = settings.home
    (home / "agents" / "pong").mkdir(parents=True)
    (home / "agents" / "pong" / "agent.yaml").write_text("name: Pong\n")
    shadow = CODER_MD.replace("name: Coder", "name: pong")
    kit_tree(home / ".agents", agents={"reviewer": REVIEWER_MD, "pong": shadow})
    kit_tree(home / ".claude", agents={"reviewer": CODER_MD.replace("Coder", "Reviewer")})
    profiles = {p.id: p for p in load_profiles(settings)}
    assert list(profiles) == ["default", "pong", "reviewer"]
    assert profiles["pong"].name == "Pong" and profiles["pong"].mode == "assistant"
    assert profiles["reviewer"].mode == "work"  # the later kit shadows the earlier one
    assert profiles["default"].kits == (home / ".agents", home / ".claude")


def test_agent_kit_is_read_and_the_workspace_kit_is_ignored(settings: Settings, tmp_path: Path):
    """The repository an agent works in is a data source: its `.claude/` (agents, commands,
    skills, hooks) and its `AGENTS.md` are for whoever develops it, not for the crew."""
    project = tmp_path / "project"
    root = kit_tree(project / ".claude", agents={"helper": REVIEWER_MD}, commands={"review": "r"})
    (root / "skills").mkdir()
    guard = {"matcher": "Bash", "hooks": [{"type": "command", "command": "exit 2"}]}
    (root / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": [guard]}}))
    (project / "AGENTS.md").write_text("Project rules.")
    coach_dir = settings.home / "agents" / "coach"
    aide = REVIEWER_MD.replace("name: Reviewer", "name: Aide")
    own = kit_tree(coach_dir / ".agents", agents={"aide": aide}, commands={"brief": "b"})
    (own / "settings.json").write_text(json.dumps({"hooks": {"PostToolUse": [guard]}}))
    (coach_dir / "agent.yaml").write_text(f"name: Coach\nworkspace: {project}\n")
    profiles = {p.id: p for p in load_profiles(settings)}
    assert list(profiles) == ["default", "coach", "aide"]  # `helper` never joins
    coach = profiles["coach"]
    assert [(k.root, k.scope) for k in agent_kits(coach)] == [(own, AGENT)]
    assert coach.skills_dirs == (coach_dir / "skills",)
    assert [c.name for c in coach.commands] == ["brief"]
    assert len(coach.hooks) == 1 and coach.hooks[0].cwd == coach_dir
    assert str(project / "AGENTS.md") not in coach.persona_files
    assert ("AGENTS.md", "Project rules.") not in bootstrap_sections(coach)
    described = coach.to_dict()
    assert described["hooks"] == 1
    assert [c["name"] for c in described["commands"]] == ["brief"]
    assert described["kits"] == [str(own)]
