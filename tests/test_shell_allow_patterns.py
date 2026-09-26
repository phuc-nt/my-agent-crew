"""The allow list: shell commands routine enough to run without asking.

Two halves. Reading the setting, where a pattern too broad to name a command is dropped
rather than honoured, and applying it, where the order against the ask list and against
autonomy is the whole point of the feature.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from my_agent_crew.agent.tool_gate import allowed_by_pattern, needs_decision
from my_agent_crew.agents.profile_edit import apply_patch
from my_agent_crew.agents.profile_yaml import load_yaml_profiles
from my_agent_crew.config import load_settings
from my_agent_crew.config_parse import ALLOW_PATTERN_DENYLIST, allow_patterns
from my_agent_crew.store.models import Conversation
from my_agent_crew.tools.ask_user import ASK_USER_TOOL_NAME
from my_agent_crew.tools.shell import SHELL_TOOL_NAME, ask_reason


def conv(*, autonomous: bool = False, auto_approve: tuple[str, ...] = ()) -> Conversation:
    return Conversation(
        id="c1",
        title="t",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        autonomous=autonomous,
        cost_cap_usd=1.0,
        skills=(),
        spent_usd=0.0,
        unknown_cost_calls=0,
        status="idle",
        auto_approve=auto_approve,
    )


# --- reading the setting ------------------------------------------------------------


def test_no_setting_at_all_means_an_empty_list(tmp_path: Path):
    """The old rule stays: an agent nobody told which commands are routine asks about
    all of them."""
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path)})
    assert settings.shell_allow_patterns == ()


def test_the_env_variable_is_split_on_semicolons(tmp_path: Path):
    settings = load_settings(
        env={"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_SHELL_ALLOW_PATTERNS": "git status; ls "}
    )
    assert settings.shell_allow_patterns == ("git status", "ls")


def test_a_yaml_list_is_read_when_the_env_is_absent(tmp_path: Path):
    (tmp_path / "config.yaml").write_text(
        "shell_allow_patterns:\n  - git status\n  - pytest\n", encoding="utf-8"
    )
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path)})
    assert settings.shell_allow_patterns == ("git status", "pytest")


def test_an_empty_env_value_turns_the_list_off_rather_than_taking_a_default(tmp_path: Path):
    (tmp_path / "config.yaml").write_text("shell_allow_patterns:\n  - git\n", encoding="utf-8")
    settings = load_settings(
        env={"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_SHELL_ALLOW_PATTERNS": ""}
    )
    assert settings.shell_allow_patterns == ()


def test_a_one_character_pattern_is_dropped():
    """One character matches almost every command line, so honouring it would not allow a
    shape of command, it would switch approval off."""
    assert allow_patterns("g;ls", None) == ("ls",)


# Written out rather than read from `ALLOW_PATTERN_DENYLIST`, because a test that draws
# its cases from the constant it guards passes just as happily when that constant is
# emptied — it simply stops running.
@pytest.mark.parametrize("pattern", ["*", ".*", ".", "-", "--", "/", "&&", "||", ";", "|"])
def test_a_pattern_that_looks_like_a_wildcard_is_dropped(pattern: str):
    assert allow_patterns(f"{pattern};git status", None) == ("git status",)


def test_every_denied_pattern_is_covered_by_the_cases_above():
    """Adding an entry to the denylist without a case here would leave it unguarded."""
    assert ALLOW_PATTERN_DENYLIST == frozenset(
        {"*", ".*", ".", "-", "--", "/", "&&", "||", ";", "|"}
    )


def test_a_bad_pattern_is_dropped_rather_than_refusing_the_whole_list():
    """One typo in a list of ten must not take an agent off the air, and dropping fails
    the safe way: that command still asks."""
    assert allow_patterns("git status;*;pytest", None) == ("git status", "pytest")


def test_dropping_every_pattern_leaves_an_empty_list_not_an_error():
    assert allow_patterns("*;.;-", None) == ()


# --- applying it --------------------------------------------------------------------


def test_an_allowed_command_runs_outside_an_autonomous_conversation():
    """The point of the list: a supervised agent gets on with the routine parts."""
    assert needs_decision(conv(), SHELL_TOOL_NAME, None, True) is False


def test_the_same_command_without_the_list_still_asks():
    assert needs_decision(conv(), SHELL_TOOL_NAME, None, False) is True


def test_the_ask_list_beats_the_allow_list():
    """Someone who names `rm -rf` dangerous and `git` routine means `git reset --hard`
    to ask, not to run."""
    assert needs_decision(conv(), SHELL_TOOL_NAME, "git reset --hard", True) is True


def test_the_ask_list_beats_the_allow_list_in_an_autonomous_conversation_too():
    assert needs_decision(conv(autonomous=True), SHELL_TOOL_NAME, "rm -rf", True) is True


def test_a_question_is_asked_even_when_everything_else_would_let_it_through():
    """A question that approved itself would be answered by nobody."""
    assert needs_decision(conv(autonomous=True), ASK_USER_TOOL_NAME, None, True) is True


def test_an_autonomous_conversation_still_runs_a_command_no_list_mentions():
    assert needs_decision(conv(autonomous=True), SHELL_TOOL_NAME, None, False) is False


def test_a_tool_the_person_always_allows_still_runs():
    assert needs_decision(conv(auto_approve=("web_search",)), "web_search", None, False) is False


class FakeDeps:
    """`allowed_by_pattern` reads nothing but the settings, so a real registry and store would only
    obscure what the test is about."""

    def __init__(self, patterns: tuple[str, ...]):
        self.settings = SimpleNamespace(shell_allow_patterns=patterns)


def test_only_a_shell_call_is_matched_against_the_allow_list():
    """Every other tool is allowed per tool, through `auto_approve`, never per argument.
    Matching a pattern against another tool's arguments would allow a whole tool because
    one field happened to contain the text."""
    deps = FakeDeps(("git status",))
    assert allowed_by_pattern(deps, SHELL_TOOL_NAME, {"command": "git status"}) is True
    assert allowed_by_pattern(deps, "shell_write", {"command": "git status"}) is False


def test_a_shell_call_with_no_command_is_not_allowed():
    assert allowed_by_pattern(FakeDeps(("git status",)), SHELL_TOOL_NAME, {}) is False


def test_an_empty_allow_list_allows_nothing():
    assert allowed_by_pattern(FakeDeps(()), SHELL_TOOL_NAME, {"command": "git status"}) is False


def test_the_two_real_agents_are_unchanged_by_default(tmp_path: Path):
    """The setting is opt-in: adding it must not have loosened an agent that never
    mentions it."""
    (tmp_path / "agents" / "worker").mkdir(parents=True)
    (tmp_path / "agents" / "worker" / "agent.yaml").write_text(
        "name: Worker\nmode: work\n", encoding="utf-8"
    )
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path)})
    for profile in load_yaml_profiles(settings):
        assert profile.settings.shell_allow_patterns == ()


def test_a_profile_may_name_its_own_routine_commands(tmp_path: Path):
    (tmp_path / "agents" / "worker").mkdir(parents=True)
    (tmp_path / "agents" / "worker" / "agent.yaml").write_text(
        "name: Worker\nshell_allow_patterns:\n  - git status\n", encoding="utf-8"
    )
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path)})
    worker = next(p for p in load_yaml_profiles(settings) if p.id == "worker")
    assert worker.settings.shell_allow_patterns == ("git status",)
    assert worker.to_dict()["shell_allow_patterns"] == ["git status"]


def test_a_patch_writing_a_bare_string_is_refused(tmp_path: Path):
    """A string is iterable, so the parser would read "git" as the patterns "g", "i" and
    "t", each short enough to be dropped — the agent would end up with an empty list and
    no word about why."""
    with pytest.raises(ValueError):
        apply_patch({}, {"shell_allow_patterns": "git status"})


def test_the_allow_list_matches_a_shape_not_a_whole_command():
    """`ask_reason` is a substring match, which is what lets one pattern cover the family
    of commands a person means by it."""
    assert ask_reason("cd repo && git status --short", ("git status",)) == "git status"


def test_a_pattern_the_command_does_not_contain_does_not_match():
    assert ask_reason("git push", ("git status",)) is None


def test_matching_ignores_case():
    assert ask_reason("GIT STATUS", ("git status",)) == "git status"
