"""A skill that drives a command-line program is only useful when the program is there
and the model knows the syntax. These cover both halves: the missing-binary label that
survives from loader to index to body, and the help hint that stops the guessing."""

from __future__ import annotations

from pathlib import Path

from my_agent_crew import texts
from my_agent_crew.agent.prompt import build_system_prompt, skill_index_section
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.config import Route, Settings
from my_agent_crew.scheduler.jobs import Job, prompt_skills
from my_agent_crew.skills import Skill, load_skills, mentioned_skills
from my_agent_crew.skills.loader import check_bins, parse_skill

WITH_BINS = """---
name: gws-shared
description: Google Workspace qua CLI
requires:
  bins: [gws, jq]
cliHelp: gws --help
---
Thân kỹ năng.
"""

PLAIN = """---
name: viet-bao-cao
description: Viết báo cáo
---
Thân kỹ năng.
"""

ONE_BIN_AS_STRING = """---
name: chay-jq
description: Lọc JSON
requires:
  bins: jq
---
Thân.
"""


def _nothing_installed(name: str) -> str | None:
    return None


def _all_installed(name: str) -> str | None:
    return f"/usr/bin/{name}"


def test_frontmatter_carries_required_bins_and_help_command() -> None:
    skill = parse_skill(WITH_BINS, "fallback")
    assert skill.requires_bins == ("gws", "jq")
    assert skill.cli_help == "gws --help"


def test_a_skill_without_the_keys_declares_nothing() -> None:
    """The common case: most skills drive no binary and must not grow a label."""
    skill = parse_skill(PLAIN, "fallback")
    assert skill.requires_bins == ()
    assert skill.cli_help == ""
    assert check_bins(skill, _nothing_installed).missing_bins == ()


def test_one_binary_may_be_written_without_list_syntax() -> None:
    assert parse_skill(ONE_BIN_AS_STRING, "fallback").requires_bins == ("jq",)


def test_a_present_binary_leaves_the_body_untouched() -> None:
    skill = check_bins(parse_skill(WITH_BINS, "x"), _all_installed)
    assert skill.missing_bins == ()
    assert skill.body == "Thân kỹ năng."


def test_a_missing_binary_warns_inside_the_body_not_only_the_index() -> None:
    """The model reads the body when it is about to run the command; a label back in the
    index it skimmed several steps ago is not where the warning has to be."""
    skill = check_bins(parse_skill(WITH_BINS, "x"), _nothing_installed)
    assert skill.missing_bins == ("gws", "jq")
    assert "gws, jq" in skill.body
    assert skill.body.endswith("Thân kỹ năng.")


def test_a_missing_binary_never_removes_the_skill(tmp_path: Path) -> None:
    """Dropping it would leave the agent with no way to learn why the job cannot run."""
    (tmp_path / "gws-shared.md").write_text(WITH_BINS, encoding="utf-8")
    loaded = load_skills(tmp_path, which=_nothing_installed)
    assert [s.name for s in loaded] == ["gws-shared"]
    assert loaded[0].missing_bins == ("gws", "jq")


def test_a_folder_skill_keeps_its_bins_and_help(tmp_path: Path) -> None:
    """The folder branch rebuilds the skill; the new fields must survive that."""
    folder = tmp_path / "gws-shared"
    folder.mkdir()
    (folder / "SKILL.md").write_text(WITH_BINS, encoding="utf-8")
    skill = load_skills(tmp_path, which=_nothing_installed)[0]
    assert skill.requires_bins == ("gws", "jq")
    assert skill.cli_help == "gws --help"
    assert skill.missing_bins == ("gws", "jq")
    assert skill.path == str(folder.resolve())


def test_index_line_labels_the_missing_binary_and_the_help_command() -> None:
    skill = check_bins(parse_skill(WITH_BINS, "x"), _nothing_installed)
    line = skill_index_section([skill])
    assert "[thiếu: gws, jq]" in line
    assert "gws --help" in line


def test_index_line_of_an_ordinary_skill_gains_nothing() -> None:
    line = skill_index_section([parse_skill(PLAIN, "x")])
    assert "thiếu" not in line
    assert line.strip().endswith("Viết báo cáo")


def test_the_prompt_tells_the_model_to_read_help_before_guessing() -> None:
    """The failure this exists for: a run spending its whole step budget trying flags."""
    base = {"home": "/tmp/x", "routes": (Route("fake", "echo"),)}
    prompt = build_system_prompt(Settings(**base, language="vi"), [], ["shell_run"])
    assert texts.CLI_GUESS_RULE in prompt
    english = build_system_prompt(Settings(**base, language="en"), [], ["shell_run"])
    assert texts.CLI_GUESS_RULE_EN in english


def test_a_prompt_naming_a_skill_attaches_it() -> None:
    skills = [Skill(name="gws-shared", description="", body="b")]
    assert mentioned_skills("Chạy gws-shared rồi tổng hợp", skills) == ["gws-shared"]


def test_a_single_word_skill_name_never_auto_attaches() -> None:
    """ "ledger" or "read" appears in prompts that have nothing to do with the skill, and a
    wrongly attached body costs the job context for nothing."""
    skills = [Skill(name="ledger", description="", body="b")]
    assert mentioned_skills("Kiểm tra ledger tháng này", skills) == []


def test_an_always_on_skill_is_not_attached_twice() -> None:
    skills = [Skill(name="gws-shared", description="", body="b", always=True)]
    assert mentioned_skills("chạy gws-shared", skills) == []


def test_a_scheduled_job_keeps_the_skills_it_listed_and_adds_the_one_it_named() -> None:
    """A job runs with nobody watching: a skill named in the prompt but missing from
    `skills:` used to leave the model guessing the command until the step cap."""
    job = Job(
        id="pong/weekly-review",
        agent_id="pong",
        schedule=Schedule("weekly-review", "Tuần", every="1w", prompt="chạy gws-shared rồi tóm"),
    )
    skills = [
        Skill(name="gws-shared", description="", body="b"),
        Skill(name="viet-bao-cao", description="", body="b"),
    ]
    assert prompt_skills(job, skills) == ["gws-shared"]


def test_a_job_does_not_list_the_same_skill_twice() -> None:
    job = Job(
        id="pong/x",
        agent_id="pong",
        schedule=Schedule("x", "x", every="1w", prompt="gws-shared", skills=("gws-shared",)),
    )
    skills = [Skill(name="gws-shared", description="", body="b")]
    assert prompt_skills(job, skills) == ["gws-shared"]


def test_skill_dict_carries_the_binary_state_to_the_web() -> None:
    data = check_bins(parse_skill(WITH_BINS, "x"), _nothing_installed).to_dict()
    assert data["requires_bins"] == ["gws", "jq"]
    assert data["missing_bins"] == ["gws", "jq"]
    assert data["cli_help"] == "gws --help"
