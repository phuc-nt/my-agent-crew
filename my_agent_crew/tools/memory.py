"""File-based memory, the same shape a person could keep by hand: `MEMORY.md` for
durable facts and `memory/YYYY-MM-DD.md` for daily notes. `memory_save` appends to
today's note; `memory_search` greps all of them. Both files enter the prompt each turn."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from my_agent_crew import texts
from my_agent_crew.agents.context import daily_note_path
from my_agent_crew.memory import user_store
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


def search_facts(user_dir: Path, terms: list[str]) -> list[tuple[str, str]]:
    """Shared facts about the person, matched on description and body rather than line by
    line: a fact is one thought, so a hit reports the whole thing, not the line it landed on."""
    hits: list[tuple[str, str]] = []
    for fact in user_store.list_facts(user_dir):
        haystack = f"{fact.description}\n{fact.body}".lower()
        if all(t in haystack for t in terms):
            summary = fact.description or fact.body.strip().splitlines()[0]
            hits.append((f"user/{fact.name}.md", summary.strip()))
    return hits


def search_memory(
    memory_dir: Path, memory_file: Path, query: str, user_dir: Path | None = None
) -> list[tuple[str, str]]:
    """(source, line) for every match, shared facts first and then the agent's own files,
    newest first. What the crew knows about the person outranks one agent's notes."""
    terms = [t for t in query.lower().split() if t]
    if not terms:
        return []
    hits: list[tuple[str, str]] = []
    if user_dir is not None:
        hits.extend(search_facts(user_dir, terms)[:MAX_HITS])
        if len(hits) >= MAX_HITS:
            return hits[:MAX_HITS]
    files: list[Path] = []
    if memory_file.is_file():
        files.append(memory_file)
    if memory_dir.is_dir():
        files.extend(sorted(memory_dir.glob("*.md"), reverse=True))
    for path in files:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped and all(t in stripped.lower() for t in terms):
                hits.append((path.name, stripped))
                if len(hits) >= MAX_HITS:
                    return hits
    return hits


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
    memory_dir: Path, memory_file: Path | None = None, user_dir: Path | None = None
) -> list[Tool]:
    memory_file = memory_file or memory_dir.parent / "MEMORY.md"

    async def save(args: dict[str, Any]) -> str:
        text = str(args.get("text", "")).strip()
        if not text:
            raise ToolError("ghi chú trống")
        append_daily_note(memory_dir, text)
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


def today_note(memory_dir: Path) -> Path:
    return daily_note_path(memory_dir, date.today())
