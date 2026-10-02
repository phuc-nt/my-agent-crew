"""Behaviour evals: play written cases against the crew's own agents and real model, on a copy.

    export OPENROUTER_API_KEY=...        # the one secret the eval server is given
    uv run python scripts/run_evals.py --runs 3 --max-usd 0.5

A case (see `scripts/eval_example_cases.yaml`) is a short conversation with one agent plus what
must, and must not, happen in it: the tools it calls, what it asks approval for, what it says.
Cases live in the live home's `evals/` folder, beside the agents they test.

Nothing runs on the live crew. The live home and the workspaces its agents use are copied into
`<out>/run`, a server starts on the copy on `--port` with no schedules, no Telegram and no
secrets file, and both are gone at the end unless `--keep-home`. Every case is played `--runs`
times, because a model does not answer the same way twice: two runs in three must pass. Each
run starts from the server the first one found, with no conversation, canvas or memory note an
earlier run left (`eval_reset.py`). Once `--max-usd` has been spent the eval stops before its
next run. `<out>/results/` keeps `results.md`, `results.json`, the server's log and, in
`transcripts/`, what each run said and made, after every run, so a run cut short still leaves
its numbers. What the agents know can be in all of them: delete them when done. `--dry-run`
swaps the model for the fake one to check the plumbing."""

from __future__ import annotations

import argparse
import contextlib
import os
import signal
import sys
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path

from eval_cases import Case
from eval_cli import (
    REPO,
    RESULTS_DIR,
    RUN_DIR,
    build_parser,
    cases_to_play,
    check_agents,
    preflight,
)
from eval_client import EvalApi
from eval_copy import remove_tree
from eval_home import EvalHome, build_home, synthetic_home
from eval_play import run_cases
from eval_report import Report, money, succeeded, summary_table
from eval_reset import MemorySnapshot, memory_roots, reset
from llm_bench_server import Server

from my_agent_crew.config import home_from


def _build_home(args: argparse.Namespace, live: Path, root: Path) -> EvalHome:
    try:
        return synthetic_home(root) if args.dry_run else build_home(live, root)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def _memory_of(eval_home: EvalHome) -> MemorySnapshot:
    """The memory files every run starts from: the copy's, as the server found them."""
    try:
        return MemorySnapshot.take(memory_roots(eval_home.home), eval_home.root)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


@contextlib.contextmanager
def _sigterm_as_interrupt() -> Iterator[None]:
    """A SIGTERM ends the eval the way Ctrl-C does: the server stops and the copy goes."""

    def interrupt(signum: int, frame: object) -> None:
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, interrupt)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def main(argv: list[str] | None = None) -> int:
    args = build_parser(__doc__.split("\n\n")[0]).parse_args(argv)
    out = args.out.expanduser().resolve()
    live = (args.home or home_from(os.environ)).expanduser()
    cases = cases_to_play(args, live)
    preflight(args, out)
    results_dir = out / RESULTS_DIR
    with _sigterm_as_interrupt():
        eval_home = _build_home(args, live, out / RUN_DIR)
        try:
            results_dir.mkdir(parents=True, exist_ok=True)
            report = Report(
                started_at=datetime.now(UTC).isoformat(timespec="seconds"),
                runs_per_case=args.runs,
                max_usd=args.max_usd,
                dry_run=args.dry_run,
                warnings=eval_home.warnings,
            )
            _announce(args, eval_home, cases)
            (results_dir / "server.log").unlink(missing_ok=True)
            server = Server(
                REPO,
                eval_home.home,
                args.port,
                extra_args=("--no-schedule",),
                extra_env={"HOME": str(eval_home.root)},
                log_path=results_dir / "server.log",
            )
            api = EvalApi(
                server.base,
                args.turn_timeout,
                eval_home.live_paths,
                turn_seconds=args.turn_timeout,
            )
            try:
                server.start()
                check_agents(api, cases)
                memory = _memory_of(eval_home)
                run_cases(api, cases, report, results_dir, fresh=lambda: reset(api, memory))
            finally:
                server.stop()
        finally:
            if args.keep_home:
                print(f"copy kept in {eval_home.root}: it holds your agents' data, delete it")
            else:
                remove_tree(eval_home.root)
    _print_summary(report, results_dir)
    return 0 if succeeded(report) else 1


def _announce(args: argparse.Namespace, eval_home: EvalHome, cases: Sequence[Case]) -> None:
    if args.dry_run:
        print("dry run: the fake model answers; only the plumbing is being checked")
    size = eval_home.size_bytes / 1e6
    print(f"copy: {eval_home.files} files, {size:.1f} MB in {eval_home.root}")
    for warning in eval_home.warnings:
        print(f"  warning: {warning}")
    print(f"cases: {', '.join(case.id for case in cases)} ({args.runs} runs each)", flush=True)


def _print_summary(report: Report, results_dir: Path) -> None:
    print("\n" + summary_table(report))
    print(f"\nspent {money(report)} of ${report.max_usd:.2f}")
    if report.stopped:
        print(f"stopped by {report.stopped}")
    print(f"results: {results_dir / 'results.md'}")


if __name__ == "__main__":
    sys.exit(main())
