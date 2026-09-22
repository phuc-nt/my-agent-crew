"""The two markdown dashboards written beside the vault.

They are files rather than an API response because the person reading them is as likely
to be in their editor as in the web UI, and because a file can be opened next year. They
are regenerated whole on every compile: a dashboard that accumulates would keep reporting
problems that were fixed months ago, which is how a report stops being read.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from my_agent_crew.memory import wiki_lint, wiki_store

REPORTS_DIRNAME = "reports"
OPEN_QUESTIONS_NAME = "open-questions.md"
STALE_NAME = "stale.md"

_SORT_LABELS = {
    "unsourced": "Không có nguồn",
    "dangling": "Liên kết tới trang chưa có",
    "review": "Cần xem lại",
    "stale": "Lâu không cập nhật",
}


def reports_dir(memory_dir: Path) -> Path:
    return wiki_store.wiki_dir(memory_dir) / REPORTS_DIRNAME


def render_questions(items: list[tuple[str, str]], today: date) -> str:
    lines = ["# Câu hỏi còn mở\n", f"Cập nhật: {today.isoformat()}\n"]
    if not items:
        lines.append("Không có câu hỏi nào đang mở.")
        return "\n".join(lines) + "\n"
    for slug, question in items:
        lines.append(f"- [[{slug}]] — {question}")
    return "\n".join(lines) + "\n"


def render_problems(problems: list[wiki_lint.Problem], today: date) -> str:
    lines = ["# Trang cần chú ý\n", f"Cập nhật: {today.isoformat()}\n"]
    if not problems:
        lines.append("Vault sạch.")
        return "\n".join(lines) + "\n"
    for sort, label in _SORT_LABELS.items():
        found = [p for p in problems if p.kind == sort]
        if not found:
            continue
        lines.append(f"\n## {label} ({len(found)})\n")
        lines.extend(f"- [[{p.slug}]] — {p.detail}" for p in found)
    return "\n".join(lines) + "\n"


def write_reports(memory_dir: Path, today: date | None = None) -> list[Path]:
    """Regenerate both dashboards. Returns what was written.

    Written even when the vault is clean: a missing file reads as "the check never ran",
    and a person who cannot tell those apart will not trust either answer.
    """
    today = today or date.today()
    pages = wiki_store.list_pages(memory_dir)
    directory = reports_dir(memory_dir)
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, text in (
        (OPEN_QUESTIONS_NAME, render_questions(wiki_lint.open_questions(pages), today)),
        (STALE_NAME, render_problems(wiki_lint.lint(memory_dir, today), today)),
    ):
        path = directory / name
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written
