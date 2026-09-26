"""What the bench asks of a model and how it scores the answer. Five turns that between
them touch every part of a turn's cost: a bare reply, a write-then-read, a shell
command, a delegation, and a read of a seeded document. Prompts are in Vietnamese
because that is what the crew's agents are spoken to in."""

from __future__ import annotations

import re
import statistics
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SALES_CSV = (
    "date,item,amount\n"
    "2026-09-01,coffee,120\n2026-09-02,lunch,340\n2026-09-03,taxi,275\n"
    "2026-09-04,books,402\n2026-09-05,dinner,450\n"
)
SALES_TOTAL = "1587"
SALES_ROWS = "5"
BRIEF_KEYWORD = "Kỳ Lân Xanh"
BRIEF_MD = f"""# Tóm tắt dự án quán cà phê

Quán cà phê **{BRIEF_KEYWORD}** mở tại quận 3 vào tháng 11, phục vụ cà phê pha máy và bánh
ngọt tự làm. Vốn ban đầu là 600 triệu đồng, trong đó 40% dành cho sửa chữa mặt bằng.

Đội ngũ gồm 4 người: một quản lý, hai pha chế và một thợ làm bánh. Giờ mở cửa dự kiến
7h đến 22h, nghỉ thứ hai đầu tháng để bảo trì máy.

Mục tiêu năm đầu là hòa vốn vào tháng thứ 9, với 180 khách mỗi ngày và hoá đơn trung
bình 65 nghìn đồng. Rủi ro lớn nhất là giá thuê mặt bằng tăng sau năm đầu.
"""
HELPER_AGENT_YAML = """name: Helper
description: Làm việc nhỏ được giao — đếm, đọc, tính trên tệp trong workspace.
mode: work
tools:
  - workspace_list
  - workspace_read
  - workspace_grep
  - shell_run
workspace: ../../workspace
routes: []
cost_cap_usd: 1.0
max_steps: 12
"""


@dataclass(frozen=True)
class Task:
    id: str
    prompt: str
    passed: Callable[[str, Path], bool]
    needs_child: bool = False


def _contains(*needles: str) -> Callable[[str, Path], bool]:
    return lambda answer, home: any(n.lower() in answer.lower() for n in needles)


def _file_and_answer(answer: str, home: Path) -> bool:
    path = home / "workspace" / "notes" / "bench.md"
    return path.is_file() and "bench ok" in path.read_text() and "bench ok" in answer.lower()


def _has_number(number: str) -> Callable[[str, Path], bool]:
    """The number as a whole token; `1.587` and `1,587` (a thousands separator in either
    convention) count as `1587`, `15870` and `0.1587` do not."""

    def passed(answer: str, home: Path) -> bool:
        plain = re.sub(r"(?<=\d)[.,](?=\d{3}(?!\d))", "", answer)
        return re.search(rf"(?<![\d.,]){number}(?![\d])", plain) is not None

    return passed


TASKS: tuple[Task, ...] = (
    Task(
        "chat",
        "Trả lời đúng một câu, không dùng công cụ: thủ đô của Việt Nam là thành phố nào?",
        _contains("hà nội", "ha noi", "hanoi"),
    ),
    Task(
        "files",
        "Tạo tệp notes/bench.md trong workspace với nội dung chính xác là dòng `bench ok`, "
        "sau đó đọc lại tệp đó và trả lời đúng nội dung vừa đọc được.",
        _file_and_answer,
    ),
    Task(
        "shell",
        "Dùng shell để tính tổng cột amount trong tệp data/sales.csv (đường dẫn tương đối "
        "trong workspace, đừng dùng đường dẫn tuyệt đối) và trả lời con số tổng.",
        _has_number(SALES_TOTAL),
    ),
    Task(
        "delegate",
        "Nhờ helper đếm số dòng dữ liệu (không tính dòng tiêu đề) trong data/sales.csv "
        "rồi báo lại cho tôi con số đó.",
        _has_number(SALES_ROWS),
        needs_child=True,
    ),
    Task(
        "summary",
        "Đọc docs/brief.md trong workspace và tóm tắt trong đúng 3 gạch đầu dòng, "
        "nhớ nhắc tên quán.",
        _contains(BRIEF_KEYWORD),
    ),
)


def seed_home(home: Path, model: str) -> None:
    """A fresh home for one model: its route, autonomy so tools do not wait on a person,
    a helper agent to delegate to, and the files the tasks read."""
    workspace = home / "workspace"
    (workspace / "data").mkdir(parents=True)
    (workspace / "docs").mkdir()
    (workspace / "data" / "sales.csv").write_text(SALES_CSV)
    (workspace / "docs" / "brief.md").write_text(BRIEF_MD)
    (home / "agents" / "helper").mkdir(parents=True)
    (home / "agents" / "helper" / "agent.yaml").write_text(HELPER_AGENT_YAML)
    route = model if ":" in model else f"openrouter:{model}"
    (home / "config.yaml").write_text(
        f"routes:\n  - {route}\nautonomous_default: true\ncost_cap_usd: 2.0\n"
    )


def score(task: Task, answer: str, home: Path, runs: list[dict[str, Any]]) -> bool:
    delegated = any(str(r.get("source", "")).startswith("delegate:") for r in runs)
    return task.passed(answer, home) and (delegated or not task.needs_child)


def metrics(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """What the run timeline says about the turn: how many model calls it took, how long
    the first token of the first call took, how much of the prompt the provider served
    from cache, and what it all cost."""
    steps = [s for r in runs for s in r.get("steps", [])]
    model_steps = [s for s in steps if s.get("kind") == "model"]
    ttfts = [s["first_token_ms"] for s in model_steps if s.get("first_token_ms") is not None]
    prompt = sum(s.get("prompt_tokens") or 0 for s in model_steps)
    cached = sum(s.get("cached_tokens") or 0 for s in model_steps)
    return {
        "model_calls": len(model_steps),
        "tool_calls": sum(1 for s in steps if s.get("kind") == "tool"),
        "child_runs": sum(1 for r in runs if str(r.get("source", "")).startswith("delegate:")),
        "ttft_first_ms": ttfts[0] if ttfts else None,
        "ttft_median_ms": int(statistics.median(ttfts)) if ttfts else None,
        "model_ms": sum(s.get("duration_ms") or 0 for s in model_steps),
        "prompt_tokens": prompt,
        "cached_tokens": cached,
        "cache_pct": round(100 * cached / prompt) if prompt else None,
        "spent_usd": round(sum(float(r.get("spent_usd") or 0) for r in runs), 5),
        "unknown_cost_calls": sum(int(r.get("unknown_cost_calls") or 0) for r in runs),
        "statuses": sorted({str(r.get("status")) for r in runs}),
    }
