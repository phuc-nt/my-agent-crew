"""Benchmark candidate models on the agent loop, away from the live crew.

    uv run python scripts/llm_bench.py --models deepseek/deepseek-v4-flash,qwen/qwen3.7-flash \\
        --out /tmp/llm-bench

Each model gets a throwaway home under `--out`, its own server on `--port` (never the
live port), no Telegram token and no live routes; only `OPENROUTER_API_KEY` is inherited.
The short tasks are in `llm_bench_tasks.py`, the multi-step and multi-delegate chains in
`llm_bench_tasks_multi.py`; `--tasks` picks a subset. Per task the bench records wall
time, model calls, time to first token, cached prompt tokens and cost, then writes
`results.json` and `results.md` after every model so a run cut short still leaves its
numbers."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from llm_bench_client import Api, Server
from llm_bench_tasks import TASKS as SHORT_TASKS
from llm_bench_tasks import metrics, score, seed_home
from llm_bench_tasks_multi import TASKS as MULTI_TASKS

TASKS = SHORT_TASKS + MULTI_TASKS

REPO = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 8797
DEFAULT_OUT = Path(tempfile.gettempdir()) / "my-agent-crew-llm-bench"
SUMMARY_COLUMNS = (
    "model",
    "passed",
    "wall_s",
    "model_calls",
    "ttft_median_ms",
    "cache_pct",
    "spent_usd",
)
COLUMNS = (
    "task",
    "ok",
    "wall_s",
    "model_calls",
    "tool_calls",
    "ttft_first_ms",
    "ttft_median_ms",
    "cache_pct",
    "prompt_tokens",
    "spent_usd",
    "error",
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--models",
        required=True,
        help="comma-separated OpenRouter model ids; `model@provider` pins an OpenRouter "
        "provider, `provider:model` names another provider",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--tasks",
        default=",".join(t.id for t in TASKS),
        help="comma-separated task ids; `short` and `multi` name the two suites",
    )
    parser.add_argument("--repeat", type=int, default=1, help="rounds per model")
    parser.add_argument("--timeout", type=float, default=240.0, help="seconds per turn")
    return parser


def slug(model: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")


def bench_model(model: str, args: argparse.Namespace, tasks: list[Any]) -> list[dict[str, Any]]:
    home = args.out / "homes" / slug(model)
    shutil.rmtree(home, ignore_errors=True)
    seed_home(home, model)
    server = Server(REPO, home, args.port)
    server.start()
    api = Api(server.base, args.timeout)
    rows: list[dict[str, Any]] = []
    try:
        for round_no in range(1, args.repeat + 1):
            for task in tasks:
                conv_id = api.create_conversation()
                turn = api.turn(conv_id, task.prompt)
                time.sleep(1.0)  # a delegated child's run may close a beat after the parent
                runs = api.runs(conv_id)
                row = {
                    "model": model,
                    "round": round_no,
                    "task": task.id,
                    "ok": score(task, turn.answer, home, runs),
                    "wall_s": turn.wall_s,
                    "approvals": turn.approvals,
                    "error": turn.error,
                    "answer": turn.answer[:300],
                    **metrics(runs),
                }
                rows.append(row)
                print(_line(row), flush=True)
    finally:
        server.stop()
    return rows


def _line(row: dict[str, Any]) -> str:
    return "  " + " | ".join(f"{c}={row.get(c)}" for c in COLUMNS if row.get(c) not in ("", None))


def summarise(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for model in dict.fromkeys(r["model"] for r in rows):
        mine = [r for r in rows if r["model"] == model]
        ttfts = [r["ttft_first_ms"] for r in mine if r["ttft_first_ms"] is not None]
        prompt = sum(r["prompt_tokens"] for r in mine)
        out.append(
            {
                "model": model,
                "passed": f"{sum(r['ok'] for r in mine)}/{len(mine)}",
                "wall_s": round(sum(r["wall_s"] for r in mine), 1),
                "model_calls": sum(r["model_calls"] for r in mine),
                "ttft_median_ms": int(statistics.median(ttfts)) if ttfts else None,
                "cache_pct": round(100 * sum(r["cached_tokens"] for r in mine) / prompt)
                if prompt
                else None,
                "spent_usd": round(sum(r["spent_usd"] for r in mine), 4),
            }
        )
    return out


def _table(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> str:
    head = "| " + " | ".join(columns) + " |\n|" + "---|" * len(columns) + "\n"
    body = "".join("| " + " | ".join(str(r.get(c, "")) for c in columns) + " |\n" for r in rows)
    return head + body


def write_results(out: Path, rows: list[dict[str, Any]]) -> None:
    (out / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    text = "# LLM bench\n\n## Per model\n\n" + _table(summarise(rows), SUMMARY_COLUMNS)
    text += "\n## Per task\n\n" + _table(rows, ("model", "round") + COLUMNS)
    (out / "results.md").write_text(text)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    suites = {"short": SHORT_TASKS, "multi": MULTI_TASKS}
    wanted = [
        t.id
        for name in args.tasks.split(",")
        for t in suites.get(name, [t for t in TASKS if t.id == name])
    ]
    tasks = [t for t in TASKS if t.id in wanted]
    if len(tasks) != len(wanted):
        raise SystemExit(f"unknown task in {wanted}; known: {[t.id for t in TASKS]}")
    args.out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for model in [m.strip() for m in args.models.split(",") if m.strip()]:
        print(f"== {model}", flush=True)
        rows.extend(bench_model(model, args, tasks))
        write_results(args.out, rows)
    print("\n" + _table(summarise(rows), SUMMARY_COLUMNS))
    print(f"results: {args.out / 'results.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
