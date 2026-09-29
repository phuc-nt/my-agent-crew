"""What an eval run says about itself: verdicts, money, why it stopped, and the files it leaves."""

from __future__ import annotations

import json

from eval_cases import Case
from eval_check import RUN, Failure
from eval_report import (
    REPLY_CHARS,
    CaseResult,
    Report,
    RunResult,
    as_json,
    markdown,
    money,
    passed_runs,
    progress_line,
    succeeded,
    summary_table,
    verdict,
)

BROKEN = Failure("calls_tool", "shell_run was never called")


def ok(number: int, spent: float = 0.0) -> RunResult:
    return RunResult(number, spent_usd=spent)


def broken(number: int, *failures: Failure) -> RunResult:
    return RunResult(number, failures or (BROKEN,))


def case_of(name: str, *runs: RunResult, agent: str = "default") -> CaseResult:
    return CaseResult(Case(name, agent, ("hi",)), list(runs))


def report_of(*cases: CaseResult, runs: int = 3, **kwargs) -> Report:
    return Report("2026-09-29T00:00:00+00:00", runs, 0.5, cases=list(cases), **kwargs)


def test_a_case_passes_when_two_runs_in_three_pass():
    report = report_of(case_of("a", ok(1), broken(2), ok(3)))

    assert verdict(report, report.cases[0]) == "pass"
    assert passed_runs(report, report.cases[0]) == 2


def test_a_case_fails_when_only_one_run_in_three_passes():
    report = report_of(case_of("a", broken(1), broken(2), ok(3)))

    assert verdict(report, report.cases[0]) == "fail"


def test_a_case_whose_last_run_was_never_played_is_incomplete_not_failed():
    report = report_of(case_of("a", ok(1), ok(2)))

    assert verdict(report, report.cases[0]) == "incomplete"


def test_the_eval_succeeds_only_when_every_case_passes_and_nothing_cut_it_short():
    passing = case_of("a", ok(1), ok(2), ok(3))
    failing = case_of("b", broken(1), broken(2), broken(3))

    assert succeeded(report_of(passing))
    assert not succeeded(report_of(passing, failing))
    assert not succeeded(report_of(passing, stopped="cap"))


def test_a_dry_run_counts_only_a_run_that_could_not_finish():
    unfinished = Failure(RUN, "timed out after 5s")
    report = report_of(
        case_of("plumbing", broken(1), broken(2), broken(3)),
        case_of("dead", broken(1, unfinished), broken(2, unfinished), broken(3, unfinished)),
        dry_run=True,
    )

    assert [verdict(report, item) for item in report.cases] == ["pass", "fail"]


def test_a_real_run_counts_every_broken_expectation():
    report = report_of(case_of("a", broken(1), broken(2), broken(3)))

    assert verdict(report, report.cases[0]) == "fail"


def test_money_is_a_plain_total_when_every_call_had_a_price():
    assert money(report_of(spent_usd=0.01234)) == "$0.0123"


def test_money_is_said_as_a_lower_bound_when_some_calls_came_back_without_a_price():
    said = money(report_of(spent_usd=0.02, unknown_cost_calls=2))

    assert said.startswith("at least $0.0200")
    assert "2 calls" in said


def test_a_run_line_shows_its_outcome_and_each_broken_expectation():
    report = report_of(case_of("a", broken(1)))

    line = progress_line(report, report.cases[0], RunResult(1, (BROKEN,), 0.0123, 4.56))

    assert line.splitlines()[0] == "  a run 1/3: FAIL (4.6s, $0.0123)"
    assert "calls_tool: shell_run was never called" in line
    assert "(not counted)" not in line


def test_a_dry_run_line_says_which_broken_expectations_are_not_counted():
    report = report_of(dry_run=True)
    report.cases = [case_of("a")]

    line = progress_line(report, report.cases[0], broken(1))

    assert line.splitlines()[0].startswith("  a run 1/3: pass")
    assert "(not counted)" in line


def test_the_summary_table_has_a_row_per_case_with_what_it_spent():
    report = report_of(
        case_of("first", ok(1, 0.001), ok(2, 0.002), ok(3, 0.003)),
        case_of("second", broken(1), broken(2), ok(3), agent="coach"),
    )

    rows = summary_table(report).splitlines()

    assert rows[0] == "| case | agent | verdict | runs passed | spent_usd |"
    assert rows[2] == "| first | default | pass | 3/3 | 0.0060 |"
    assert rows[3] == "| second | coach | fail | 1/3 | 0.0000 |"


def test_the_markdown_says_what_broke_and_in_which_run():
    report = report_of(
        case_of("fine", ok(1), ok(2), ok(3)),
        case_of("bad", broken(1), ok(2), broken(3, Failure("max_calls", "shell_run 2 > 0"))),
    )

    text = markdown(report)

    assert "## What broke" in text
    assert "### bad (fail, 1/3)" in text
    assert "- run 1: calls_tool: shell_run was never called" in text
    assert "- run 3: max_calls: shell_run 2 > 0" in text
    assert "### fine" not in text


def test_the_markdown_has_no_what_broke_section_when_nothing_broke():
    assert "What broke" not in markdown(report_of(case_of("fine", ok(1), ok(2), ok(3))))


def test_the_markdown_names_why_an_eval_stopped_early():
    text = markdown(report_of(case_of("a", ok(1)), stopped="cap"))

    assert "> Stopped by cap:" in text
    assert "budget ran out" in text
    assert "| a | default | incomplete | 1/3 |" in text


def test_the_markdown_says_a_stall_may_have_left_a_turn_running():
    text = markdown(
        report_of(case_of("a", broken(1, Failure(RUN, "timed out after 5s"))), stopped="stall")
    )

    assert "> Stopped by stall:" in text
    assert "spend into the next run" in text


def test_the_markdown_of_a_dry_run_says_only_the_plumbing_was_checked():
    text = markdown(report_of(case_of("a", broken(1), broken(2), broken(3)), dry_run=True))

    assert "> Dry run." in text
    assert "not that an agent behaves" in text
    assert "(not counted)" in text


def test_the_markdown_lists_what_the_copy_warned_about():
    text = markdown(report_of(warnings=("a schedule names /Users/x/live",)))

    assert "## About the copy" in text
    assert "- a schedule names /Users/x/live" in text


def test_the_json_carries_verdicts_money_and_a_shortened_reply():
    long_reply = "x" * (REPLY_CHARS + 50)
    item = case_of("a", RunResult(1, (BROKEN,), 0.5, 2.0, long_reply), ok(2), ok(3))
    report = report_of(item, spent_usd=0.5, unknown_cost_calls=1, warnings=("careful",))

    data = json.loads(json.dumps(as_json(report)))

    assert data["succeeded"] is True
    assert data["spent_usd"] == 0.5
    assert data["unknown_cost_calls"] == 1
    assert data["warnings"] == ["careful"]
    case = data["cases"][0]
    assert (case["id"], case["verdict"], case["passed_runs"]) == ("a", "pass", 2)
    first = case["runs"][0]
    assert first["ok"] is False
    assert len(first["reply"]) == REPLY_CHARS
    assert first["failures"] == [
        {"assertion": "calls_tool", "detail": "shell_run was never called"}
    ]
