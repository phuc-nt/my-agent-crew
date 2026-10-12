"""A markdown file whose front matter is not YAML costs that one file.

An agent, a command or a skill it defines is left out and named in the log, and a persona
is read as written. The parser's own error used to go past every reader: one such file in
the home's kit or its skills stopped the start of the whole crew, and one persona file
failed every turn of its agent."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.agents import load_profiles
from my_agent_crew.agents.context import bootstrap_sections
from my_agent_crew.agents.kit import split_front_matter
from my_agent_crew.config import load_settings
from my_agent_crew.server import build_runtime, create_app
from my_agent_crew.skills.loader import load_skills, parse_skill

# A list left open. Neither reading takes it: the second one only knows a line with a
# second colon (`test_front_matter_with_a_second_colon.py`).
ODD = "---\nname: odd\ntools: [Read, Grep\n---\nYou fix tests.\n"
GOOD = "---\nname: good\ndescription: Reads code.\n---\nYou read code.\n"
INSTALL = "/api/agents/install"


def settings_of(home: Path):
    return load_settings(env={"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"})


def serve(home: Path):
    runtime = build_runtime(settings_of(home))
    return runtime, TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1")


@pytest.fixture
def home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


def pair(folder: Path) -> Path:
    """One file that cannot be read beside one that can, the bad one first by name."""
    folder.mkdir(parents=True)
    (folder / "a-odd.md").write_text(ODD, encoding="utf-8")
    (folder / "good.md").write_text(GOOD, encoding="utf-8")
    return folder / "a-odd.md"


def test_the_reader_refuses_a_front_matter_that_is_not_yaml_as_a_value_error():
    with pytest.raises(ValueError, match="front matter is not YAML"):
        split_front_matter(ODD)


def test_a_kit_agent_is_left_out_and_named_while_the_others_load(home, caplog):
    odd = pair(home / ".agents" / "agents")

    with caplog.at_level(logging.WARNING):
        profiles = load_profiles(settings_of(home))

    assert [profile.id for profile in profiles] == ["default", "good"]
    assert str(odd) in caplog.text


def test_a_kit_command_is_left_out_and_named_while_the_others_load(home, caplog):
    odd = pair(home / ".agents" / "commands")

    with caplog.at_level(logging.WARNING):
        master = load_profiles(settings_of(home))[0]

    assert [command.name for command in master.commands] == ["good"]
    assert str(odd) in caplog.text


def test_a_skill_is_left_out_and_named_while_the_others_load(home, caplog):
    odd = pair(home / "skills")

    with caplog.at_level(logging.WARNING):
        skills = load_skills(home / "skills")

    assert [skill.name for skill in skills] == ["good"]
    assert str(odd) in caplog.text


def test_a_skill_in_a_folder_is_left_out_the_same_way(home, caplog):
    (home / "skills" / "odd").mkdir(parents=True)
    (home / "skills" / "odd" / "SKILL.md").write_text(ODD, encoding="utf-8")
    (home / "skills" / "good.md").write_text(GOOD, encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        skills = load_skills(home / "skills")

    assert [skill.name for skill in skills] == ["good"]
    assert str(home / "skills" / "odd" / "SKILL.md") in caplog.text


@pytest.mark.parametrize("front", ["just some words", "- one\n- two", "7"])
def test_a_skill_front_matter_that_states_no_keys_is_read_as_none(front):
    """It parses, into a text or a list, and the reader asked that for its keys."""
    skill = parse_skill(f"---\n{front}\n---\nThe body.\n", "plain")

    assert (skill.name, skill.description, skill.body) == ("plain", "", "The body.")
    assert skill.always is False


@pytest.mark.parametrize("where", [".agents/agents", ".agents/commands", "skills"])
def test_the_crew_starts_and_grows_beside_a_file_that_cannot_be_read(home, where):
    """Each of the three stopped the start; the two routes that read the home again
    answered with a traceback, the install after it had written."""
    _, served = serve(home)
    with served as client:
        (home / where).mkdir(parents=True, exist_ok=True)
        (home / where / "a-odd.md").write_text(ODD, encoding="utf-8")

        assert client.post("/api/agents/reload").status_code == 200
        installed = client.post(INSTALL, json={"template": "kongming"})

    assert installed.status_code == 201, installed.text
    assert "kongming" in sorted(build_runtime(settings_of(home)).agents)


def persona(home: Path, text: str):
    folder = home / "agents" / "odd"
    folder.mkdir(parents=True)
    (folder / "agent.yaml").write_text("name: Odd\npersona_files: [SOUL.md]\n", encoding="utf-8")
    (folder / "SOUL.md").write_text(text, encoding="utf-8")
    profile = next(p for p in load_profiles(settings_of(home)) if p.id == "odd")
    return dict(bootstrap_sections(profile))


def test_a_persona_whose_opening_block_is_not_yaml_is_read_as_written(home):
    """No part of what the owner wrote is dropped: a block that is not YAML is no front
    matter. Building the prompt used to fail, so the agent answered nothing at all."""
    assert persona(home, ODD)["SOUL.md"] == ODD.strip()


def test_a_persona_with_a_front_matter_keeps_only_its_body(home):
    assert persona(home, GOOD)["SOUL.md"] == "You read code."
