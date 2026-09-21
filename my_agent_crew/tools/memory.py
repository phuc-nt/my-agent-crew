"""File-based memory, the same shape a person could keep by hand: `MEMORY.md` for
durable facts and `memory/YYYY-MM-DD.md` for daily notes. `memory_save` appends to
today's note; `memory_search` looks through all of them. Both files enter the prompt each turn."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

from my_agent_crew import texts
from my_agent_crew.agents.context import daily_note_path
from my_agent_crew.memory import search, user_store
from my_agent_crew.tools.registry import Tool, ToolError

MAX_HITS = 12


def append_daily_note(memory_dir: Path, text: str, now: datetime | None = None) -> Path:
    now = now or datetime.now()
    memory_dir.mkdir(parents=True, exist_ok=True)
    path = daily_note_path(memory_dir, now.date())
    line = f"- {now.strftime('%H:%M')} {text.strip()}\n"
    if not path.exists():
        path.write_text(f"# {now.date().isoformat()}\n\n{line}", encoding="utf-8")
    else:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
    return path


def _fact_files(user_dir: Path) -> list[tuple[str, str]]:
    """A fact is one thought: its description and body search and report together."""
    return [
        (f"user/{fact.name}.md", f"{fact.description}\n{fact.body}")
        for fact in user_store.list_facts(user_dir)
    ]


def search_facts(user_dir: Path, query: str) -> list[tuple[str, str]]:
    """(source, entry) for the shared facts that match, best first."""
    return [(hit.source, hit.text) for hit in search.search(_fact_files(user_dir), query, MAX_HITS)]


def _memory_files(
    memory_dir: Path, memory_file: Path, user_dir: Path | None
) -> list[tuple[str, str]]:
    """Every file worth searching, in the order that breaks ties between equal matches:
    what the crew knows about the person outranks one agent's notes, and a fresh note
    outranks an old one."""
    files: list[tuple[str, str]] = _fact_files(user_dir) if user_dir is not None else []
    if memory_file.is_file():
        files.append((memory_file.name, memory_file.read_text(encoding="utf-8", errors="replace")))
    if memory_dir.is_dir():
        # Every markdown file in the folder, not only the dated notes: a workspace written
        # by hand keeps things like `facebook-books.md` there, and they are memory too.
        for path in sorted(memory_dir.glob("*.md"), reverse=True):
            files.append((path.name, path.read_text(encoding="utf-8", errors="replace")))
    return files


def search_memory(
    memory_dir: Path, memory_file: Path, query: str, user_dir: Path | None = None
) -> list[tuple[str, str]]:
    """(source, entry) for the best matches, shared facts first and then the agent's own
    files, newest first. See `memory.search` for what counts as one entry."""
    files = _memory_files(memory_dir, memory_file, user_dir)
    return [(hit.source, hit.text) for hit in search.search(files, query, MAX_HITS)]


def count_notes(memory_dir: Path) -> int:
    if not memory_dir.is_dir():
        return 0
    return sum(
        1
        for p in memory_dir.glob("*.md")
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.startswith("- ")
    )


def build_memory_tools(
    memory_dir: Path,
    memory_file: Path | None = None,
    user_dir: Path | None = None,
    clock: Callable[[], datetime] = datetime.now,
) -> list[Tool]:
    """`clock` decides which day a note lands on: the person's, via `Settings.now`."""
    memory_file = memory_file or memory_dir.parent / "MEMORY.md"

    async def save(args: dict[str, Any]) -> str:
        text = str(args.get("text", "")).strip()
        if not text:
            raise ToolError("ghi chú trống")
        append_daily_note(memory_dir, text, clock())
        return texts.MEMORY_SAVED.format(count=count_notes(memory_dir))

    async def search(args: dict[str, Any]) -> str:
        hits = search_memory(memory_dir, memory_file, str(args.get("query", "")), user_dir)
        if not hits:
            return texts.MEMORY_EMPTY
        return "\n".join(f"[{source}] {line}" for source, line in hits)

    return [
        Tool(
            name="memory_save",
            description=(
                "Ghi một ghi chú vào nhật ký hôm nay (memory/YYYY-MM-DD.md) để dùng lại ở các"
                " cuộc trò chuyện sau. Sự thật lâu dài thì ghi vào MEMORY.md bằng workspace_write."
            ),
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            run=save,
        ),
        Tool(
            name="memory_search",
            description=texts.MEMORY_SEARCH_DESCRIPTION,
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            run=search,
        ),
    ]


def today_note(memory_dir: Path, today: date | None = None) -> Path:
    return daily_note_path(memory_dir, today or date.today())
