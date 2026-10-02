"""Playing cases: one run on a fresh conversation, then the runs of every case, writing the
results after each so a run cut short still leaves its numbers. Each run starts from a server
put back as the first run found it (`eval_reset.py`) and leaves a transcript of what it did
beside the results. A canvas step between two messages is not a turn: it is what the person
does in the panel (`eval_canvas.py`)."""

from __future__ import annotations

import contextlib
import json
import re
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import httpx
from eval_canvas import CanvasStep, Panel, perform
from eval_cases import Case
from eval_check import RUN, Failure, check
from eval_client import EvalApi
from eval_observe import child_ids, observe
from eval_report import CaseResult, Report, RunResult, as_json, markdown, progress_line
from eval_reset import RESET_FAILED, ResetError
from llm_bench_client import HTTP_FAILED, TIMED_OUT

SETTLE_SECONDS = 1.0  # a delegated child's run, and a side call, may land a beat after the turn
TRANSCRIPTS = "transcripts"
_UNSAFE = re.compile(r"[^\w.-]+")  # what a case id may hold and a file name should not


def play(api: EvalApi, case: Case, number: int, transcript: Path | None = None) -> RunResult:
    """One run of a case on a fresh conversation, judged against the case's expectations. What
    the run left, its conversation, the children's, its canvases and what it asked, is written
    to `transcript` when there is one."""
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
    canvases = [api.artifact(str(a["id"])) for a in api.artifacts(conv_id)]
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
    if transcript is not None:
        kept = {"case": case.id, "run": number, "conversation": conversation}
        kept |= {"children": children, "canvases": canvases, "asked": api.asked}
        _write_json(transcript, kept)
    failures = tuple(check(case, observed))
    return RunResult(number, failures, observed.spent_usd, round(wall, 1), observed.reply)


def stalled(result: RunResult) -> bool:
    """A run that timed out, or lost the server, may have left a turn running: it could spend
    into the next run's window, so the eval does not go on. Nor does it once a run could not
    start from a clean server: what an earlier run left would judge the rest."""
    return any(
        f.assertion == RUN and f.detail.startswith((TIMED_OUT, HTTP_FAILED, RESET_FAILED))
        for f in result.failures
    )


def run_cases(
    api: EvalApi,
    cases: Sequence[Case],
    report: Report,
    results_dir: Path,
    fresh: Callable[[], None],
) -> None:
    """Every run of every case, each after `fresh` has put the server back as it was."""
    report.cases = [CaseResult(case) for case in cases]
    start, start_unknown = api.ledger()
    for index, item in enumerate(report.cases, 1):
        for number in range(1, report.runs_per_case + 1):
            if not report.stopped and report.spent_usd >= report.max_usd:
                report.stopped = "cap"
            if report.stopped:
                break
            name = f"{index:02d}-{_UNSAFE.sub('_', item.case.id)}-{number}.json"
            transcript = results_dir / TRANSCRIPTS / name
            result = _play_or_fail(api, item.case, number, fresh, transcript)
            item.runs.append(result)
            _count_spending(api, report, start, start_unknown)
            print(progress_line(report, item, result), flush=True)
            if stalled(result):
                report.stopped = "stall"
            write_results(results_dir, report)
    time.sleep(SETTLE_SECONDS)
    _count_spending(api, report, start, start_unknown)
    write_results(results_dir, report)


def _play_or_fail(
    api: EvalApi, case: Case, number: int, fresh: Callable[[], None], transcript: Path
) -> RunResult:
    try:
        fresh()
        return play(api, case, number, transcript)
    except httpx.HTTPError as exc:
        return RunResult(number, (Failure(RUN, f"{HTTP_FAILED} {exc}"),))
    except ResetError as exc:
        return RunResult(number, (Failure(RUN, str(exc)),))


def _count_spending(api: EvalApi, report: Report, start: float, start_unknown: int) -> None:
    """The ledger since the eval began: the truth about cost, side calls included."""
    with contextlib.suppress(httpx.HTTPError):
        spent, unknown = api.ledger()
        report.spent_usd, report.unknown_cost_calls = spent - start, unknown - start_unknown


def write_results(results_dir: Path, report: Report) -> None:
    _write_json(results_dir / "results.json", as_json(report))
    (results_dir / "results.md").write_text(markdown(report), encoding="utf-8")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
