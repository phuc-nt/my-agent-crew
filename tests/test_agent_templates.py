"""The bundled agent templates: what they declare, what installing one writes, and the
scan that keeps a foreign tool name from creeping into a persona."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from my_agent_crew.agents import templates_cli
from my_agent_crew.agents.profile import ASSISTANT, MODES
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

EXPECTED = {"researcher"}
# No bundled template names another one. The lead and its adviser below are written for the
# tests that add a template with the peers it delegates to, beside the bundled ones.
LEAD, ADVISER = "lead", "adviser"
CREW = {LEAD, ADVISER, "researcher"}
SHARED = "workspace: ../../workspace\nskills_dirs:\n  - ../../skills\n"
LEAD_YAML = f"name: Lead\nmode: work\ndelegates:\n  - {ADVISER}\n  - researcher\n{SHARED}"
ADVISER_YAML = f"name: Adviser\nmode: work\ntools:\n  - workspace_read\n  - skill_read\n{SHARED}"
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


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home to add into, with a lead that delegates to two peers among the templates."""
    bundled = tmp_path / "bundled"
    shutil.copytree(TEMPLATES_DIR, bundled)
    for name, manifest in ((LEAD, LEAD_YAML), (ADVISER, ADVISER_YAML)):
        (bundled / name).mkdir()
        (bundled / name / MANIFEST).write_text(manifest, encoding="utf-8")
    monkeypatch.setattr(templates_cli, "TEMPLATES_DIR", bundled)
    return tmp_path / "home"


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


def test_a_template_says_who_it_delegates_to_and_which_tools_it_keeps(home):
    listed = {t.id: t for t in list_templates()}
    assert set(listed) == CREW
    assert set(listed[LEAD].delegates) == CREW - {LEAD}
    assert listed[LEAD].tools == ()  # no allow-list: the lead keeps `delegate`
    assert listed[ADVISER].tools == ("workspace_read", "skill_read")


def test_the_researcher_stays_out_of_work_mode():
    modes = {t.id: t.mode for t in list_templates()}
    assert modes == {"researcher": ASSISTANT}


def test_the_researcher_cannot_edit_code_and_does_not_delegate():
    """It reads the web and writes a report; an edit tool would let research turn into
    changes nobody asked it to make."""
    [researcher] = list_templates()
    tools = set(researcher.tools)
    assert tools and not tools & {"workspace_edit", DELEGATE_TOOL_NAME}
    assert researcher.delegates == ()


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
    agent_dir, peers = add_template("researcher", tmp_path)

    assert agent_dir == tmp_path / "agents" / "researcher" and peers == []
    assert (agent_dir / "agent.yaml").is_file() and (agent_dir / "AGENTS.md").is_file()
    assert (tmp_path / "skills" / "delegation.md").is_file()


def test_an_id_may_differ_from_the_template_name(tmp_path):
    agent_dir, _ = add_template("researcher", tmp_path, agent_id="scout")

    assert agent_dir == tmp_path / "agents" / "scout"
    raw = yaml.safe_load((agent_dir / "agent.yaml").read_text(encoding="utf-8"))
    assert raw["name"] == "Researcher" and raw["mode"] == ASSISTANT


def test_adding_twice_refuses_unless_forced(tmp_path):
    """An edited profile is the user's work; a second add must not quietly discard it."""
    agent_dir, _ = add_template("researcher", tmp_path)
    (agent_dir / "agent.yaml").write_text("name: Mine\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        add_template("researcher", tmp_path)
    assert (agent_dir / "agent.yaml").read_text(encoding="utf-8") == "name: Mine\n"

    add_template("researcher", tmp_path, force=True)
    assert "Researcher" in (agent_dir / "agent.yaml").read_text(encoding="utf-8")


def test_adding_a_lead_brings_the_peers_it_delegates_to(home):
    """The server refuses to start when a `delegates` entry names an agent that is not
    there, so a lead added on its own would leave a home that cannot come up."""
    agent_dir, peers = add_template(LEAD, home)

    assert agent_dir.is_dir()
    assert set(peers) == CREW - {LEAD}
    for peer in peers:
        assert (home / "agents" / peer / MANIFEST).is_file()


def test_a_peer_that_is_already_there_is_left_alone(home):
    add_template(ADVISER, home)
    (home / "agents" / ADVISER / MANIFEST).write_text("name: Mine\n", encoding="utf-8")

    _, peers = add_template(LEAD, home)

    assert peers == ["researcher"]
    assert (home / "agents" / ADVISER / MANIFEST).read_text(encoding="utf-8") == "name: Mine\n"


def test_an_unknown_template_is_refused_before_anything_is_written(tmp_path):
    with pytest.raises(KeyError):
        add_template("architect", tmp_path)
    assert not (tmp_path / "agents").exists()


def test_an_installed_crew_starts_and_the_lead_can_reach_its_peers(home):
    """The whole point of the templates: add the lead, start, and delegation is wired."""
    add_template(LEAD, home)
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}

    rt = build_runtime(load_settings(env=env))

    assert set(rt.agents) == CREW | {"default"}
    lead = rt.deps_for(LEAD)
    assert DELEGATE_TOOL_NAME in lead.tools.names()
    assert set(lead.agent.delegates) == CREW - {LEAD}
    # The allow-listed roles keep only what they asked for, and no peer may delegate on.
    # The script tool comes with what was asked for: it calls the tools among them that read.
    for agent_id in CREW - {LEAD}:
        peer = rt.deps_for(agent_id)
        assert set(peer.tools.names()) == {*peer.agent.tools, "tool_script"}, agent_id
        assert peer.tools.names()[-1] == "tool_script", agent_id
        assert DELEGATE_TOOL_NAME not in peer.tools.names(), agent_id
    # Every role reads the one shared set, so a skill is installed once, not per agent,
    # and all of them work where the master does until a workspace is pinned.
    for agent_id in CREW:
        assert "delegation" in {s.name for s in rt.deps_for(agent_id).skills}, agent_id
        assert rt.deps_for(agent_id).agent.workspace == rt.default.agent.workspace, agent_id


def test_a_pinned_workspace_reaches_the_lead_and_every_peer_it_brings(home, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    agent_dir, peers = add_template(LEAD, home, workspace=repo)

    assert set(peers) == CREW - {LEAD}
    for directory in (agent_dir, *(home / "agents" / p for p in peers)):
        text = (directory / MANIFEST).read_text(encoding="utf-8")
        assert f"workspace: {repo.resolve()}" in text, directory.name
    brought = (home / "agents" / "researcher" / MANIFEST).read_text(encoding="utf-8")
    assert "# The crew shares one set of skills" in brought  # comments survive the rewrite


def test_every_tool_a_template_lists_is_a_real_tool(tmp_path):
    """A name that no tool answers to is dropped with a warning at startup, so the role
    silently loses a capability. Installing every template and comparing catches it here."""
    for template in EXPECTED:
        add_template(template, tmp_path)
    env = {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"}

    rt = build_runtime(load_settings(env=env))

    for agent_id in EXPECTED:
        deps = rt.deps_for(agent_id)
        assert deps.agent.tools and set(deps.agent.tools) <= set(deps.tools.names()), agent_id


def test_the_researcher_can_read_a_long_output_back(tmp_path):
    add_template("researcher", tmp_path)
    env = {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"}

    rt = build_runtime(load_settings(env=env))

    assert "tool_output_read" in rt.deps_for("researcher").tools.names()
    assert rt.deps_for("researcher").tools.spill is not None
