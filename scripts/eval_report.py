"""What an eval run reports: a verdict per case, the money spent, and why it stopped early.

Pure: `eval_play.py` fills in a `Report` as it plays; this module turns it into the lines it
prints and the files it writes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eval_cases import Case
from eval_check import RUN, Failure, case_passed

STOP_NOTES = {
    "cap": "the budget ran out before every run was played",
    "stall": (
        "a turn timed out or the server stopped answering, so the eval was abandoned: a turn "
        "still running could otherwise spend into the next run"
    ),
}
DRY_RUN_NOTE = (
    "The fake model answers, so only a run that could not finish counts: the other "
    "expectations below show that the plumbing works, not that an agent behaves."
)
REPLY_CHARS = 400


@dataclass(frozen=True)
class RunResult:
    number: int
    failures: tuple[Failure, ...] = ()
    spent_usd: float = 0.0
    wall_s: float = 0.0
    reply: str = ""


@dataclass
class CaseResult:
    case: Case
    runs: list[RunResult] = field(default_factory=list)


@dataclass
class Report:
    started_at: str
    runs_per_case: int
    max_usd: float
    dry_run: bool = False
    warnings: tuple[str, ...] = ()
    cases: list[CaseResult] = field(default_factory=list)
    stopped: str = ""
    spent_usd: float = 0.0
    unknown_cost_calls: int = 0


def counted(report: Report, result: RunResult) -> tuple[Failure, ...]:
    """The failures that decide a verdict. On a dry run the fake model keeps no expectation,
    so only a run that could not finish counts."""
    return tuple(f for f in result.failures if not report.dry_run or f.assertion == RUN)


def passed_runs(report: Report, item: CaseResult) -> int:
    return sum(1 for run in item.runs if not counted(report, run))


def verdict(report: Report, item: CaseResult) -> str:
    """`pass`, `fail`, or `incomplete` when the eval stopped before the case's last run."""
    if len(item.runs) < report.runs_per_case:
        return "incomplete"
    outcomes = [not counted(report, run) for run in item.runs]
    return "pass" if case_passed(outcomes, report.runs_per_case) else "fail"


def succeeded(report: Report) -> bool:
    return not report.stopped and all(verdict(report, c) == "pass" for c in report.cases)


def money(report: Report) -> str:
    """The total, said as a lower bound when the provider gave no price for some calls."""
    if report.unknown_cost_calls:
        calls = report.unknown_cost_calls
        return f"at least ${report.spent_usd:.4f} ({calls} calls came back without a price)"
    return f"${report.spent_usd:.4f}"


def progress_line(report: Report, item: CaseResult, run: RunResult) -> str:
    """What the runner prints when a run ends: its outcome, then each broken expectation."""
    ok = not counted(report, run)
    head = f"  {item.case.id} run {run.number}/{report.runs_per_case}: {'pass' if ok else 'FAIL'}"
    lines = [f"{head} ({run.wall_s:.1f}s, ${run.spent_usd:.4f})"]
    kept = counted(report, run)
    lines += [f"      {f}{'' if f in kept else ' (not counted)'}" for f in run.failures]
    return "\n".join(lines)


def summary_table(report: Report) -> str:
    rows = [
        (
            item.case.id,
            item.case.agent,
            verdict(report, item),
            f"{passed_runs(report, item)}/{report.runs_per_case}",
            f"{sum(run.spent_usd for run in item.runs):.4f}",
        )
        for item in report.cases
    ]
    return _table(("case", "agent", "verdict", "runs passed", "spent_usd"), rows)


def markdown(report: Report) -> str:
    lines = [
        "# Behaviour evals",
        "",
        f"Started {report.started_at}: {report.runs_per_case} runs per case, "
        f"budget ${report.max_usd:.2f}, spent {money(report)}.",
        "",
    ]
    if report.dry_run:
        lines += [f"> Dry run. {DRY_RUN_NOTE}", ""]
    if report.stopped:
        lines += [f"> Stopped by {report.stopped}: {STOP_NOTES[report.stopped]}.", ""]
    lines += [summary_table(report)]
    broken = [item for item in report.cases if any(run.failures for run in item.runs)]
    if broken:
        lines += ["", "## What broke", ""]
    for item in broken:
        label = f"{verdict(report, item)}, {passed_runs(report, item)}/{report.runs_per_case}"
        lines += [f"### {item.case.id} ({label})", ""]
        for run in item.runs:
            kept = counted(report, run)
            for failure in run.failures:
                note = "" if failure in kept else " (not counted)"
                lines.append(f"- run {run.number}: {failure}{note}")
        lines.append("")
    if report.warnings:
        lines += ["## About the copy", ""] + [f"- {warning}" for warning in report.warnings]
    return "\n".join(lines).rstrip() + "\n"


def as_json(report: Report) -> dict[str, Any]:
    return {
        "started_at": report.started_at,
        "runs_per_case": report.runs_per_case,
        "max_usd": report.max_usd,
        "dry_run": report.dry_run,
        "stopped": report.stopped,
        "spent_usd": round(report.spent_usd, 6),
        "unknown_cost_calls": report.unknown_cost_calls,
        "succeeded": succeeded(report),
        "warnings": list(report.warnings),
        "cases": [_case_json(report, item) for item in report.cases],
    }


def _case_json(report: Report, item: CaseResult) -> dict[str, Any]:
    return {
        "id": item.case.id,
        "agent": item.case.agent,
        "verdict": verdict(report, item),
        "passed_runs": passed_runs(report, item),
        "runs": [
            {
                "run": run.number,
                "ok": not counted(report, run),
                "spent_usd": round(run.spent_usd, 6),
                "wall_s": run.wall_s,
                "reply": run.reply[:REPLY_CHARS],
                "failures": [{"assertion": f.assertion, "detail": f.detail} for f in run.failures],
            }
            for run in item.runs
        ],
    }


def _table(columns: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    head = "| " + " | ".join(columns) + " |\n|" + "---|" * len(columns) + "\n"
    return head + "".join("| " + " | ".join(row) + " |\n" for row in rows).rstrip("\n")
