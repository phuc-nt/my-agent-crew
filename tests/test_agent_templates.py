"""The bundled agent templates: what they declare, what installing one writes, and the
scan that keeps a foreign tool name from creeping into a persona."""

from __future__ import annotations

import pytest
import yaml

from my_agent_crew.agents.profile import ASSISTANT, MODES, WORK
from my_agent_crew.agents.profile_yaml import parse_profile
from my_agent_crew.agents.templates_cli import (
    MANIFEST,
    SHARED_SKILLS,
    TEMPLATES_DIR,
    add_template,
    list_templates,
)
from my_agent_crew.config import Settings, load_settings
from my_agent_crew.server import build_runtime
from my_agent_crew.tools.delegate import DELEGATE_TOOL_NAME

EXPECTED = {
    "dev",
    "scout",
    "planner",
    "coder",
    "reviewer",
    "tester",
    "debugger",
    "researcher",
    "git",
}
# Names from other agent harnesses. A persona that keeps one of these tells the model to
# call a tool that does not exist here, and the failure only shows up mid-task.
FOREIGN = (
    "Task(",
    "TaskCreate",
    "TaskList",
    "SendMessage",
    "MultiEdit",
    "WebSearch",
    "WebFetch",
    "repomix",
    "gemini",
    "/mk:",
    ".claude/",
)
MAX_PERSONA_LINES = 120


def _template_dirs():
    return [TEMPLATES_DIR / t.id for t in list_templates()]


def test_every_expected_template_ships():
    assert {t.id for t in list_templates()} == EXPECTED


def test_each_template_loads_as_a_profile(settings: Settings):
    """The manifests are parsed by the same code that reads a hand-written one, so a bad
    key fails here rather than at startup on someone's machine."""
    base = settings
    for directory in _template_dirs():
        raw = yaml.safe_load((directory / "agent.yaml").read_text(encoding="utf-8"))
        profile = parse_profile(directory.name, directory, raw, base)
        assert profile.mode in MODES
        assert profile.description, f"{directory.name} has no description"


def test_the_lead_delegates_to_every_other_template():
    [dev] = [t for t in list_templates() if t.id == "dev"]
    assert set(dev.delegates) == EXPECTED - {"dev"}
    assert dev.tools == ()  # no allow-list: the lead keeps `delegate`


def test_only_the_researcher_stays_out_of_work_mode():
    modes = {t.id: t.mode for t in list_templates()}
    assert modes.pop("researcher") == ASSISTANT
    assert set(modes.values()) == {WORK}


def test_the_reviewer_cannot_edit_and_the_scout_cannot_write():
    tools = {t.id: set(t.tools) for t in list_templates()}
    assert "workspace_edit" not in tools["reviewer"]
    assert "workspace_write" not in tools["scout"] and "shell_run" not in tools["scout"]
    assert tools["git"] == {"shell_run"}


def test_personas_name_no_tool_from_another_harness():
    for directory in _template_dirs():
        for path in sorted(directory.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            found = [n for n in FOREIGN if n in text]
            assert not found, f"{path.name} in {directory.name} mentions {found}"


def test_shared_skills_name_no_tool_from_another_harness():
    for path in sorted((TEMPLATES_DIR / SHARED_SKILLS).glob("*.md")):
        text = path.read_text(encoding="utf-8")
        found = [n for n in FOREIGN if n in text]
        assert not found, f"{path.name} mentions {found}"


def test_personas_stay_short_enough_to_be_read_every_turn():
    for directory in _template_dirs():
        for path in sorted(directory.glob("*.md")):
            lines = path.read_text(encoding="utf-8").splitlines()
            assert len(lines) <= MAX_PERSONA_LINES, f"{directory.name}/{path.name}: {len(lines)}"


def test_every_shared_skill_has_a_name_and_a_description():
    from my_agent_crew.skills.loader import parse_skill

    paths = sorted((TEMPLATES_DIR / SHARED_SKILLS).glob("*.md"))
    assert paths
    for path in paths:
        skill = parse_skill(path.read_text(encoding="utf-8"), path.stem)
        assert skill.name and skill.description, path.name


def test_adding_a_template_writes_the_agent_and_the_shared_skills(tmp_path):
    agent_dir, peers = add_template("scout", tmp_path)

    assert agent_dir == tmp_path / "agents" / "scout" and peers == []
    assert (agent_dir / "agent.yaml").is_file() and (agent_dir / "AGENTS.md").is_file()
    assert (tmp_path / "skills" / "delegation.md").is_file()


def test_an_id_may_differ_from_the_template_name(tmp_path):
    agent_dir, _ = add_template("coder", tmp_path, agent_id="backend")

    assert agent_dir == tmp_path / "agents" / "backend"
    raw = yaml.safe_load((agent_dir / "agent.yaml").read_text(encoding="utf-8"))
    assert raw["mode"] == WORK


def test_adding_twice_refuses_unless_forced(tmp_path):
    """An edited profile is the user's work; a second add must not quietly discard it."""
    agent_dir, _ = add_template("scout", tmp_path)
    (agent_dir / "agent.yaml").write_text("name: Mine\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        add_template("scout", tmp_path)
    assert (agent_dir / "agent.yaml").read_text(encoding="utf-8") == "name: Mine\n"

    add_template("scout", tmp_path, force=True)
    assert "Scout" in (agent_dir / "agent.yaml").read_text(encoding="utf-8")


def test_adding_a_lead_brings_the_peers_it_delegates_to(tmp_path):
    """The server refuses to start when a `delegates` entry names an agent that is not
    there, so a lead added on its own would leave a home that cannot come up."""
    agent_dir, peers = add_template("dev", tmp_path)

    assert agent_dir.is_dir()
    assert set(peers) == EXPECTED - {"dev"}
    for peer in peers:
        assert (tmp_path / "agents" / peer / MANIFEST).is_file()


def test_a_peer_that_is_already_there_is_left_alone(tmp_path):
    add_template("scout", tmp_path)
    (tmp_path / "agents" / "scout" / MANIFEST).write_text("name: Mine\n", encoding="utf-8")

    _, peers = add_template("dev", tmp_path)

    assert "scout" not in peers
    assert (tmp_path / "agents" / "scout" / MANIFEST).read_text(encoding="utf-8") == "name: Mine\n"


def test_an_unknown_template_is_refused_before_anything_is_written(tmp_path):
    with pytest.raises(KeyError):
        add_template("architect", tmp_path)
    assert not (tmp_path / "agents").exists()


def test_an_installed_crew_starts_and_the_lead_can_reach_its_peers(tmp_path):
    """The whole point of the templates: add the lead, start, and delegation is wired."""
    add_template("dev", tmp_path)
    env = {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"}

    rt = build_runtime(load_settings(env=env))

    assert set(rt.agents) == EXPECTED | {"default"}
    dev = rt.deps_for("dev")
    assert DELEGATE_TOOL_NAME in dev.tools.names()
    assert set(dev.agent.delegates) == EXPECTED - {"dev"}
    # The allow-listed roles keep only what they asked for, and no peer may delegate on.
    assert set(rt.deps_for("scout").tools.names()) == set(rt.deps_for("scout").agent.tools)
    assert DELEGATE_TOOL_NAME not in rt.deps_for("scout").tools.names()
    # Every role reads the one shared set, so a skill is installed once, not nine times.
    for agent_id in EXPECTED:
        assert "delegation" in {s.name for s in rt.deps_for(agent_id).skills}, agent_id
