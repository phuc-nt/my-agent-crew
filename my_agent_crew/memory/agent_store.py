"""One agent's own memory as files: `MEMORY.md` and the dated notes beside it.

The same files the agent reads at the start of every turn, so editing them here is
editing what it will know next time — no separate copy, no sync step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class NoteInfo:
    day: str
    chars: int

    def to_dict(self) -> dict[str, object]:
        return {"day": self.day, "chars": self.chars}


def check_day(day: str) -> str:
    """A note is named after its date; anything else would let a path out of the folder."""
    if not DAY_PATTERN.match(day):
        raise ValueError(f"ngày không hợp lệ: {day}")
    return day


def read_memory_md(memory_file: Path) -> str:
    return memory_file.read_text(encoding="utf-8") if memory_file.is_file() else ""


def write_memory_md(memory_file: Path, text: str) -> None:
    memory_file.parent.mkdir(parents=True, exist_ok=True)
    memory_file.write_text(text, encoding="utf-8")


def list_notes(memory_dir: Path) -> list[NoteInfo]:
    """Newest day first, so the panel opens on what just happened."""
    if not memory_dir.is_dir():
        return []
    notes = [
        NoteInfo(day=path.stem, chars=len(path.read_text(encoding="utf-8", errors="replace")))
        for path in memory_dir.glob("*.md")
        if DAY_PATTERN.match(path.stem)
    ]
    return sorted(notes, key=lambda n: n.day, reverse=True)


def read_note(memory_dir: Path, day: str) -> str:
    path = memory_dir / f"{check_day(day)}.md"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def write_note(memory_dir: Path, day: str, text: str) -> None:
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / f"{check_day(day)}.md").write_text(text, encoding="utf-8")
