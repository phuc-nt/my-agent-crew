"""The eval command line: its options, which cases it plays, and what it refuses up front."""

from __future__ import annotations

import argparse
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from eval_cases import Case, load_cases
from eval_client import EvalApi
from llm_bench_server import port_is_free

REPO = Path(__file__).resolve().parent.parent
EXAMPLE_CASES = REPO / "scripts" / "eval_example_cases.yaml"
DEFAULT_PORT = 8798
DEFAULT_OUT = Path(tempfile.gettempdir()) / "my-agent-crew-evals"
MODEL_KEY = "OPENROUTER_API_KEY"
RUN_DIR = "run"
RESULTS_DIR = "results"


def build_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--cases",
        type=Path,
        help="a case file, or a folder of them (default: <home>/evals; the example cases "
        "with --dry-run)",
    )
    parser.add_argument(
        "--home", type=Path, help="the home to copy (default: MY_AGENT_HOME, else ~/.my-agent-crew)"
    )
    parser.add_argument("--only", help="comma-separated case ids to play")
    parser.add_argument("--runs", type=int, default=3, help="times each case is played")
    parser.add_argument(
        "--max-usd", type=float, default=0.5, help="stop before the next run once this is spent"
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--turn-timeout", type=float, default=300.0, help="seconds a turn may take, all told"
    )
    parser.add_argument("--keep-home", action="store_true", help="leave the copy in <out>/run")
    parser.add_argument("--dry-run", action="store_true", help="fake model: check the plumbing")
    return parser


def cases_to_play(args: argparse.Namespace, live: Path) -> list[Case]:
    path = args.cases or (EXAMPLE_CASES if args.dry_run else live / "evals")
    try:
        cases = load_cases(path)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if not args.only:
        return cases
    wanted = [name.strip() for name in args.only.split(",") if name.strip()]
    known = [case.id for case in cases]
    if unknown := [name for name in wanted if name not in known]:
        raise SystemExit(f"no such case: {', '.join(unknown)}; the cases are: {', '.join(known)}")
    return [case for case in cases if case.id in wanted]


def preflight(args: argparse.Namespace, out: Path) -> None:
    """Everything that can be refused before a byte is copied or a cent is spent."""
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")
    if args.max_usd <= 0:
        raise SystemExit("--max-usd must be more than 0: a budget of nothing plays nothing")
    if out == REPO or out.is_relative_to(REPO):
        raise SystemExit(
            f"--out {out} is inside the repository, where a commit could take the copy"
        )
    if not port_is_free(args.port):
        raise SystemExit(f"port {args.port} is busy: stop its owner first, it is not mine")
    if not args.dry_run and not os.environ.get(MODEL_KEY):
        raise SystemExit(
            f"{MODEL_KEY} is not exported in this shell: the eval server gets its model key "
            "from here and from nowhere else"
        )
    if (out / RUN_DIR).exists():
        raise SystemExit(
            f"{out / RUN_DIR} is left from an earlier run: remove it or pick another --out"
        )


def check_agents(api: EvalApi, cases: Sequence[Case]) -> None:
    known = api.agent_ids()
    if missing := sorted({case.agent for case in cases} - set(known)):
        raise SystemExit(
            f"no such agent in the copy: {', '.join(missing)}; the agents are: {', '.join(known)}"
        )
