"""A front matter line with a second colon is read as the text it is.

`description: Use when: the tests fail` is the shape a description takes in many a kit
written for another harness, and YAML refuses it. A block YAML takes is still exactly
what YAML made of it; only a block it refuses is read again, each such line as text."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from my_agent_crew.agents import load_profiles
from my_agent_crew.agents.context import bootstrap_sections
from my_agent_crew.agents.kit import split_front_matter
from my_agent_crew.config import load_settings
from my_agent_crew.skills.loader import load_skills

WHOLE = "Use when: the tests fail"
COLON = f"---\nname: fixer\ndescription: {WHOLE}\n---\nYou fix tests.\n"


def settings_of(home: Path):
    return load_settings(env={"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"})


@pytest.fixture
def home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


def placed(folder: Path, text: str = COLON) -> Path:
    folder.mkdir(parents=True)
    (folder / "fixer.md").write_text(text, encoding="utf-8")
    return folder / "fixer.md"


def stated(front: str) -> dict:
    meta, body = split_front_matter(f"---\n{front}\n---\nThe body.\n")
    assert body == "The body."
    return meta


def test_a_description_with_a_second_colon_arrives_whole():
    assert split_front_matter(COLON) == ({"name": "fixer", "description": WHOLE}, "You fix tests.")


def test_a_kit_agent_whose_description_holds_a_colon_joins_the_crew(home, caplog):
    path = placed(home / ".agents" / "agents")

    with caplog.at_level(logging.WARNING):
        fixer = next(p for p in load_profiles(settings_of(home)) if p.id == "fixer")

    assert fixer.description == WHOLE
    assert str(path) not in caplog.text


def test_a_kit_command_whose_description_holds_a_colon_is_a_command(home, caplog):
    path = placed(home / ".agents" / "commands")

    with caplog.at_level(logging.WARNING):
        (command,) = load_profiles(settings_of(home))[0].commands

    assert (command.name, command.description, command.template) == (
        "fixer",
        WHOLE,
        "You fix tests.",
    )
    assert str(path) not in caplog.text


@pytest.mark.parametrize("as_folder", [False, True])
def test_a_skill_whose_description_holds_a_colon_is_loaded(home, caplog, as_folder):
    folder = home / "skills" / "fixer" if as_folder else home / "skills"
    folder.mkdir(parents=True)
    path = folder / ("SKILL.md" if as_folder else "fixer.md")
    path.write_text(COLON, encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        (skill,) = load_skills(home / "skills")

    assert (skill.name, skill.description) == ("fixer", WHOLE)
    assert skill.body.endswith("You fix tests.")
    assert str(path) not in caplog.text


def test_a_persona_whose_front_matter_holds_such_a_line_keeps_only_its_body(home):
    """The block is a front matter now, so the model is not handed it."""
    folder = home / "agents" / "fixer"
    folder.mkdir(parents=True)
    (folder / "agent.yaml").write_text("name: Fixer\npersona_files: [SOUL.md]\n", encoding="utf-8")
    (folder / "SOUL.md").write_text(COLON, encoding="utf-8")
    profile = next(p for p in load_profiles(settings_of(home)) if p.id == "fixer")

    assert dict(bootstrap_sections(profile))["SOUL.md"] == "You fix tests."


@pytest.mark.parametrize(
    "text",
    [
        "Use when:",
        "Use when:\tthe tests fail",
        "Dùng khi: kiểm thử hỏng — đủ dấu, có cả chữ đ và 😀",
        'Say "done": then leave C:\\temp alone',
        "--dry-run: change nothing",
        "Use when: one: two: three",
    ],
)
def test_the_text_of_such_a_line_arrives_as_written(text):
    assert stated(f"name: fixer\ndescription: {text}") == {"name": "fixer", "description": text}


def test_blanks_after_the_text_are_not_part_of_it():
    assert stated("description: Use when:  \t") == {"description": "Use when:"}


def test_the_rest_of_such_a_line_is_its_text_a_remark_included():
    """Whoever left the second colon unquoted was not writing YAML: `#12` is a part of
    the sentence."""
    whole = "Use when: fixing issue #12 # see the tracker"

    assert stated(f"description: {whole}") == {"description": whole}


def test_a_block_yaml_reads_is_what_yaml_made_of_it():
    front = (
        "name: reader\n"
        "enabled: true\n"
        "max_steps: 5\n"
        "tools: [Read, Grep]\n"
        "delegates:\n"
        "  - fixer\n"
        'description: "Use when: the code is unread"\n'
        "note: 'Ask: then read'\n"
        "ratio: 0.5 # of what: nobody says\n"
        "link: http://example.test/a:b"
    )

    assert stated(front) == {
        "name": "reader",
        "enabled": True,
        "max_steps": 5,
        "tools": ["Read", "Grep"],
        "delegates": ["fixer"],
        "description": "Use when: the code is unread",
        "note": "Ask: then read",
        "ratio": 0.5,
        "link": "http://example.test/a:b",
    }


def test_a_line_inside_a_value_yaml_reads_is_never_taken_as_text():
    """A quoted value may run over lines, and one of them may look like `key: text: more`.
    YAML reads the block, so nothing reads it a second time."""
    assert stated("note: 'one\ntwo: three: four\nfive'") == {"note": "one two: three: four five"}


def test_beside_a_line_read_as_text_every_other_line_keeps_what_yaml_makes_of_it():
    front = (
        f"description: {WHOLE}\n"
        "enabled: true\n"
        "max_steps: 5\n"
        "tools: [Read, Grep]\n"
        "ratio: 0.5 # of what: nobody says\n"
        "delegates:\n"
        "  - fixer"
    )

    assert stated(front) == {
        "description": WHOLE,
        "enabled": True,
        "max_steps": 5,
        "tools": ["Read", "Grep"],
        "ratio": 0.5,
        "delegates": ["fixer"],
    }


@pytest.mark.parametrize(
    "front",
    [
        "metadata:\n  note: Use when: the tests fail",  # a nested key
        "description: Use when: the tests\n  fail twice",  # a value over two lines
        "tools:\n- Read: when: asked",  # an item of a list
        "- Read: when: asked",
        "description: - Use when: asked",
        "description: ? Use when: asked",
        '"description": Use when: asked',  # a key written as YAML
        "see:also: Use when: asked",  # a key holding a colon
        "description: Use when: asked\ntools: [Read, Grep",  # broken somewhere else as well
    ]
    + [f"description: {mark}Use when: asked" for mark in "[{|>&*!%@`'\""],
)
def test_a_block_the_second_reading_does_not_know_is_still_refused(front):
    with pytest.raises(ValueError, match="front matter is not YAML"):
        stated(front)


def test_the_refusal_names_what_is_still_in_the_way():
    """Not the line with the second colon, which the second reading took."""
    with pytest.raises(ValueError, match="line 3"):
        stated(f"name: fixer\ndescription: {WHOLE}\ntools: [Read, Grep")
