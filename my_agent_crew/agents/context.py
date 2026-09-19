"""What an agent reads at the start of every turn: its persona files, its long-term
memory file and the daily notes for today and yesterday. Files are re-read each turn so
an edit on disk takes effect on the next message, no restart."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from my_agent_crew.agents.profile import AgentProfile

MAX_SECTION_CHARS = 24000
DAILY_NOTE_FORMAT = "%Y-%m-%d"


def _read_capped(path: Path) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return None
    if len(text) > MAX_SECTION_CHARS:
        text = text[:MAX_SECTION_CHARS] + "\n…"
    return text


def daily_note_path(memory_dir: Path, day: date) -> Path:
    return memory_dir / f"{day.strftime(DAILY_NOTE_FORMAT)}.md"


def bootstrap_sections(profile: AgentProfile, today: date | None = None) -> list[tuple[str, str]]:
    """(title, body) pairs in the order they enter the system prompt."""
    today = today or date.today()
    sections: list[tuple[str, str]] = []
    for name in profile.persona_files:
        body = _read_capped(profile.dir / name)
        if body:
            sections.append((name, body))
    memory = _read_capped(profile.memory_file)
    if memory:
        sections.append(("MEMORY.md", memory))
    for day in (today - timedelta(days=1), today):
        path = daily_note_path(profile.memory_dir, day)
        body = _read_capped(path)
        if body:
            sections.append((f"memory/{path.name}", body))
    return sections


def ensure_agent_dirs(profile: AgentProfile) -> None:
    for path in (profile.dir, profile.workspace, profile.memory_dir):
        path.mkdir(parents=True, exist_ok=True)
