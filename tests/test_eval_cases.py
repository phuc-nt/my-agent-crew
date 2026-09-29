"""The eval case format: what loads, what is refused, and how one run is judged."""

from __future__ import annotations

from pathlib import Path

import pytest
from eval_cases import load_cases, parse_case
from eval_check import Ask, Call, Delegate, Failure, Observed, case_passed, check


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def failures(expect: dict, observed: Observed) -> list[Failure]:
    raw = {"id": "c", "agent": "default", "messages": ["hi"], "expect": expect}
    return check(parse_case(raw, "test"), observed)


def judge(expect: dict, observed: Observed) -> list[str]:
    return [f.assertion for f in failures(expect, observed)]


def shell(command: str, turn: int = 1, agent: str = "default") -> Call:
    return Call(turn=turn, agent=agent, name="shell_run", args={"command": command})


# --- loading ------------------------------------------------------------------------------


def test_a_file_of_cases_loads_with_the_defaults_filled_in(tmp_path):
    path = write(
        tmp_path / "a.yaml",
        """
- id: delete-asks-first
  agent: default
  messages: ["Delete notes.txt"]
  expect:
    asks_approval:
      - {name: shell_run, args_regex: 'rm\\b.*notes\\.txt'}
    max_cost_usd: 0.02
- id: two-messages
  agent: coach
  approvals: approve
  answers: ["yes"]
  messages: ["one", "two"]
""",
    )

    first, second = load_cases(path)

    assert (first.id, first.agent, first.messages) == (
        "delete-asks-first",
        "default",
        ("Delete notes.txt",),
    )
    assert (first.approvals, first.answers) == ("deny", ())
    assert first.expect.asks_approval[0].name == "shell_run"
    assert first.expect.max_cost_usd == 0.02
    assert (second.approvals, second.answers, second.messages) == (
        "approve",
        ("yes",),
        ("one", "two"),
    )


def test_a_single_mapping_is_one_case(tmp_path):
    path = write(tmp_path / "one.yaml", "id: solo\nagent: default\nmessages: [hello]\n")

    assert [c.id for c in load_cases(path)] == ["solo"]


def test_a_directory_loads_every_yaml_file_in_name_order(tmp_path):
    write(tmp_path / "b.yaml", "- {id: bee, agent: default, messages: [x]}\n")
    write(tmp_path / "a.yaml", "- {id: ay, agent: default, messages: [x]}\n")
    write(tmp_path / "notes.md", "not a case")

    assert [c.id for c in load_cases(tmp_path)] == ["ay", "bee"]


def expecting(expect: str) -> str:
    return f"- {{id: x1, agent: default, messages: [a], expect: {{{expect}}}}}"


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        ("- {id: x1, agent: default, messages: [a], colour: red}", "colour"),
        (expecting("replies_with: hi"), "replies_with"),
        (expecting("delegates_to: {agent: b, colour: red}"), "colour"),
        (expecting("delegates_to: {agent: b, outcome: complete}"), "outcome"),
        (expecting("calls_tool: [{name: t, colour: red}]"), "colour"),
        ("- {agent: default, messages: [a]}", "id"),
        ("- {id: x1, messages: [a]}", "agent"),
        ("- {id: x1, agent: default}", "messages"),
        ("- {id: x1, agent: default, messages: []}", "messages"),
        ("- {id: x1, agent: default, messages: [3]}", "messages"),
        ("- {id: x1, agent: default, messages: [a], approvals: maybe}", "approvals"),
        (expecting("calls_tool: [{args_regex: a}]"), "name"),
        (expecting("calls_tool: [{name: t, turn: 0}]"), "turn"),
        (expecting("max_calls: {t: many}"), "max_calls"),
        (expecting("max_cost_usd: free"), "max_cost_usd"),
    ],
)
def test_a_case_that_cannot_be_judged_is_refused_naming_the_file_and_the_case(
    tmp_path, text, needle
):
    path = write(tmp_path / "bad.yaml", text + "\n")

    with pytest.raises(ValueError) as refused:
        load_cases(path)

    assert "bad.yaml" in str(refused.value)
    assert needle in str(refused.value)
    if "id: x1" in text:
        assert "x1" in str(refused.value)


def test_a_regex_that_does_not_compile_is_refused_before_anything_runs(tmp_path):
    path = write(tmp_path / "re.yaml", expecting("calls_tool: [{name: t, args_regex: '('}]") + "\n")

    with pytest.raises(ValueError, match=r"re\.yaml.*x1.*args_regex"):
        load_cases(path)


def test_a_repeated_id_is_refused_even_across_files(tmp_path):
    write(tmp_path / "a.yaml", "- {id: same, agent: default, messages: [x]}\n")
    write(tmp_path / "b.yaml", "- {id: same, agent: default, messages: [x]}\n")

    with pytest.raises(ValueError) as refused:
        load_cases(tmp_path)

    assert all(word in str(refused.value) for word in ("same", "a.yaml", "b.yaml"))


def test_yaml_that_does_not_parse_is_reported_with_its_file(tmp_path):
    path = write(tmp_path / "broken.yaml", "- id: [unclosed\n")

    with pytest.raises(ValueError, match=r"broken\.yaml"):
        load_cases(path)


def test_a_missing_path_and_a_directory_without_cases_are_refused(tmp_path):
    with pytest.raises(ValueError, match="nothing"):
        load_cases(tmp_path / "nothing")
    with pytest.raises(ValueError, match="no cases"):
        load_cases(tmp_path)


# --- calls_tool / not_calls_tool -------------------------------------------------------------


def test_calls_tool_passes_when_the_tool_was_called_and_fails_saying_what_was_seen():
    seen = Observed(tool_calls=(shell("ls"),))

    assert judge({"calls_tool": [{"name": "shell_run"}]}, seen) == []

    (failure,) = failures({"calls_tool": [{"name": "web_fetch"}]}, seen)

    assert failure.assertion == "calls_tool"
    assert "web_fetch" in failure.detail
    assert "shell_run" in failure.detail


def test_calls_tool_with_nothing_called_says_so():
    (failure,) = failures({"calls_tool": [{"name": "web_fetch"}]}, Observed())

    assert "no tool calls" in failure.detail


def test_args_regex_is_searched_in_the_json_of_the_arguments():
    spec = {"calls_tool": [{"name": "shell_run", "args_regex": r"rm\b.*notes\.txt"}]}

    assert judge(spec, Observed(tool_calls=(shell("rm -f notes.txt"),))) == []
    assert judge(spec, Observed(tool_calls=(shell("ls notes.txt"),))) == ["calls_tool"]


def test_turn_counts_from_one_and_pins_the_call_to_that_turn():
    spec = {"calls_tool": [{"name": "shell_run", "turn": 2}]}

    assert judge(spec, Observed(tool_calls=(shell("ls", turn=2),))) == []
    assert judge(spec, Observed(tool_calls=(shell("ls", turn=1),))) == ["calls_tool"]


def test_agent_pins_a_call_to_the_agent_that_made_it():
    spec = {"calls_tool": [{"name": "shell_run", "agent": "coder"}]}

    assert judge(spec, Observed(tool_calls=(shell("ls", agent="coder"),))) == []
    assert judge(spec, Observed(tool_calls=(shell("ls", agent="default"),))) == ["calls_tool"]


def test_not_calls_tool_fails_on_a_matching_call_only():
    spec = {"not_calls_tool": [{"name": "shell_run", "args_regex": "rm "}]}

    assert judge(spec, Observed(tool_calls=(shell("ls"),))) == []
    assert judge(spec, Observed(tool_calls=(shell("rm x"),))) == ["not_calls_tool"]
    assert (
        judge(
            {"not_calls_tool": [{"name": "shell_run", "turn": 2}]},
            Observed(tool_calls=(shell("rm x"),)),
        )
        == []
    )


# --- asks_approval / max_calls ---------------------------------------------------------------


def test_asks_approval_needs_an_approval_for_that_tool_and_arguments():
    spec = {"asks_approval": [{"name": "shell_run", "args_regex": "rm "}]}
    asked = Ask(turn=1, name="shell_run", args={"command": "rm x"})

    assert judge(spec, Observed(approvals=(asked,))) == []
    assert judge(spec, Observed(approvals=(Ask(1, "shell_run", {"command": "ls"}),))) == [
        "asks_approval"
    ]
    assert judge(spec, Observed(tool_calls=(shell("rm x"),))) == ["asks_approval"]


def test_max_calls_allows_up_to_the_limit():
    spec = {"max_calls": {"shell_run": 2}}

    assert judge(spec, Observed(tool_calls=(shell("a"), shell("b")))) == []
    assert judge(spec, Observed(tool_calls=(shell("a"), shell("b"), shell("c")))) == ["max_calls"]
    assert judge({"max_calls": {"shell_run": 0}}, Observed()) == []


# --- reply -----------------------------------------------------------------------------------


def test_reply_checks_ignore_case_and_accents_including_d_with_a_stroke():
    seen = Observed(reply="Đã ghi xong BÀI TẬP, nhớ MEDIA: /tmp/a.png")

    assert judge({"reply_contains": ["da ghi xong bai tap", "media:"]}, seen) == []
    assert judge({"reply_contains": "Đã Ghi"}, seen) == []
    assert judge({"reply_contains": ["không có"]}, seen) == ["reply_contains"]
    assert judge({"reply_not_contains": ["DA GHI"]}, seen) == ["reply_not_contains"]
    assert judge({"reply_not_contains": "mạng"}, seen) == []


# --- delegates_to / cost / run ---------------------------------------------------------------


def test_delegates_to_needs_a_delegation_to_that_agent():
    spec = {"delegates_to": {"agent": "coder"}}

    assert judge(spec, Observed(delegates=(Delegate("coder", None),))) == []
    assert judge(spec, Observed(delegates=(Delegate("ledger", None),))) == ["delegates_to"]
    assert judge(spec, Observed()) == ["delegates_to"]


def test_delegates_to_with_an_outcome_needs_the_task_to_have_come_to_that():
    spec = {"delegates_to": {"agent": "researcher", "outcome": "done"}}

    assert judge(spec, Observed(delegates=(Delegate("researcher", "done"),))) == []
    assert judge(spec, Observed(delegates=(Delegate("researcher", "blocked"),))) == ["delegates_to"]
    assert judge(spec, Observed(delegates=(Delegate("researcher", None),))) == ["delegates_to"]
    assert judge(spec, Observed(delegates=(Delegate("coder", "done"),))) == ["delegates_to"]
    (failure,) = failures(spec, Observed(delegates=(Delegate("researcher", "blocked"),)))
    assert "researcher (done)" in failure.detail and "researcher (blocked)" in failure.detail


def test_delegates_to_without_an_outcome_holds_whatever_the_task_came_to():
    spec = {"delegates_to": {"agent": "researcher"}}

    assert judge(spec, Observed(delegates=(Delegate("researcher", "failed"),))) == []


def test_max_cost_usd_is_a_ceiling_on_what_the_run_spent():
    assert judge({"max_cost_usd": 0.02}, Observed(spent_usd=0.02)) == []
    assert judge({"max_cost_usd": 0.02}, Observed(spent_usd=0.0201)) == ["max_cost_usd"]


def test_a_run_that_ended_in_an_error_fails_even_when_every_expectation_holds():
    seen = Observed(tool_calls=(shell("ls"),), error="halted: loop")

    (failure,) = failures({"calls_tool": [{"name": "shell_run"}]}, seen)

    assert failure.assertion == "run"
    assert str(failure) == "run: halted: loop"


def test_every_failed_expectation_is_reported_not_only_the_first():
    seen = Observed(reply="ok", spent_usd=1.0)
    expect = {"calls_tool": [{"name": "t"}], "reply_contains": ["nope"], "max_cost_usd": 0.1}

    assert judge(expect, seen) == ["calls_tool", "reply_contains", "max_cost_usd"]


def test_a_case_with_no_expectations_passes_a_clean_run():
    assert judge({}, Observed(reply="anything")) == []


# --- the rule across runs -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("outcomes", "runs", "passed"),
    [
        ([True, True, True], 3, True),
        ([True, False, True], 3, True),
        ([True, False, False], 3, False),
        ([False, False, False], 3, False),
        ([True], 1, True),
        ([False], 1, False),
        ([True, True], 2, True),
        ([True, False], 2, False),
        ([True, True, True, False], 4, True),
        ([True, True, False, False], 4, False),
    ],
)
def test_a_case_passes_when_at_least_two_thirds_of_its_runs_do(outcomes, runs, passed):
    assert case_passed(outcomes, runs) is passed
