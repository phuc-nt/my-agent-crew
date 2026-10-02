"""Playing cases: one run on a fresh conversation, then the runs of every case, writing the
results after each so a run cut short still leaves its numbers. A canvas step between two
messages is not a turn: it is what the person does in the panel (`eval_canvas.py`)."""

from __future__ import annotations

import contextlib
import json
import time
from collections.abc import Sequence
from pathlib import Path

import httpx
from eval_canvas import CanvasStep, Panel, perform
from eval_cases import Case
from eval_check import RUN, Failure, check
from eval_client import EvalApi
from eval_observe import child_ids, observe
from eval_report import CaseResult, Report, RunResult, as_json, markdown, progress_line
from llm_bench_client import HTTP_FAILED, TIMED_OUT

SETTLE_SECONDS = 1.0  # a delegated child's run, and a side call, may land a beat after the turn


def play(api: EvalApi, case: Case, number: int) -> RunResult:
    """One run of a case on a fresh conversation, judged against the case's expectations."""
    cost_before, unknown_before = api.ledger()
    conv_id = api.create_conversation(case.agent, autonomous=False)
    api.start_case(case.approvals, case.answers)
    panel, error, wall = Panel(), "", 0.0
    for item in case.messages:
        if isinstance(item, CanvasStep):
            error = perform(api, conv_id, item, panel)
        else:
            turn = api.turn(conv_id, item, **panel.carry())
            wall += turn.wall_s
            error = turn.error
        if error:
            break
    time.sleep(SETTLE_SECONDS)
    conversation = api.conversation(conv_id)
    children = [api.conversation(child) for child in child_ids(api.runs(conv_id), conv_id)]
    canvases = [api.artifact(str(a["id"])).get("content") or "" for a in api.artifacts(conv_id)]
    cost_after, unknown_after = api.ledger()
    observed = observe(
        conversation,
        children,
        api.asked,
        cost_after - cost_before,
        unknown_after - unknown_before,
        error,
        canvases,
    )
    failures = tuple(check(case, observed))
    return RunResult(number, failures, observed.spent_usd, round(wall, 1), observed.reply)


def stalled(result: RunResult) -> bool:
    """A run that timed out, or lost the server, may have left a turn running: it could spend
    into the next run's window, so the eval does not go on."""
    return any(
        f.assertion == RUN and f.detail.startswith((TIMED_OUT, HTTP_FAILED))
        for f in result.failures
    )


def run_cases(api: EvalApi, cases: Sequence[Case], report: Report, results_dir: Path) -> None:
    report.cases = [CaseResult(case) for case in cases]
    start, start_unknown = api.ledger()
    for item in report.cases:
        for number in range(1, report.runs_per_case + 1):
            if not report.stopped and report.spent_usd >= report.max_usd:
                report.stopped = "cap"
            if report.stopped:
                break
            result = _play_or_fail(api, item.case, number)
            item.runs.append(result)
            _count_spending(api, report, start, start_unknown)
            print(progress_line(report, item, result), flush=True)
            if stalled(result):
                report.stopped = "stall"
            write_results(results_dir, report)
    time.sleep(SETTLE_SECONDS)
    _count_spending(api, report, start, start_unknown)
    write_results(results_dir, report)


def _play_or_fail(api: EvalApi, case: Case, number: int) -> RunResult:
    try:
        return play(api, case, number)
    except httpx.HTTPError as exc:
        return RunResult(number, (Failure(RUN, f"{HTTP_FAILED} {exc}"),))


def _count_spending(api: EvalApi, report: Report, start: float, start_unknown: int) -> None:
    """The ledger since the eval began: the truth about cost, side calls included."""
    with contextlib.suppress(httpx.HTTPError):
        spent, unknown = api.ledger()
        report.spent_usd, report.unknown_cost_calls = spent - start, unknown - start_unknown


def write_results(results_dir: Path, report: Report) -> None:
    (results_dir / "results.json").write_text(
        json.dumps(as_json(report), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (results_dir / "results.md").write_text(markdown(report), encoding="utf-8")
