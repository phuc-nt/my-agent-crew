"""What an agent reads at the start of every turn: its persona files, its long-term
memory file and the daily notes for today and yesterday. Files are re-read each turn so
an edit on disk takes effect on the next message, no restart."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from my_agent_crew.agents.profile import AgentProfile
from my_agent_crew.memory import user_store
from my_agent_crew.texts import (
    PREVIOUS_SUMMARY_SECTION_TITLE,
    USER_FACTS_SECTION_TITLE,
    USER_MD_SECTION_TITLE,
)

MAX_SECTION_CHARS = 24000
# The user sections ride along in every agent's prompt, so they stay far smaller.
MAX_USER_SECTION_CHARS = 4000
DAILY_NOTE_FORMAT = "%Y-%m-%d"


def _cap(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n…"


def _read_capped(path: Path) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return _cap(text, MAX_SECTION_CHARS) if text else None


def daily_note_path(memory_dir: Path, day: date) -> Path:
    return memory_dir / f"{day.strftime(DAILY_NOTE_FORMAT)}.md"


def user_sections(user_dir: Path) -> list[tuple[str, str]]:
    """What the whole crew knows about the person: the hand-written USER.md and the index
    of remembered facts. The index rather than the facts themselves — it names every fact
    and lets the agent read the ones it needs with workspace_read."""
    sections: list[tuple[str, str]] = []
    for title, body in (
        (USER_MD_SECTION_TITLE, user_store.read_user_md(user_dir)),
        (USER_FACTS_SECTION_TITLE, user_store.read_index(user_dir)),
    ):
        if body:
            sections.append((title, _cap(body, MAX_USER_SECTION_CHARS)))
    return sections


def bootstrap_sections(
    profile: AgentProfile,
    today: date | None = None,
    previous_summary: str = "",
) -> list[tuple[str, str]]:
    """(title, body) pairs in the order they enter the system prompt."""
    today = today or date.today()
    sections: list[tuple[str, str]] = []
    for name in profile.persona_files:
        body = _read_capped(profile.dir / name)
        if body:
            sections.append((name, body))
    sections.extend(user_sections(profile.settings.user_dir))
    memory = _read_capped(profile.memory_file)
    if memory:
        sections.append(("MEMORY.md", memory))
    if previous_summary.strip():
        sections.append((PREVIOUS_SUMMARY_SECTION_TITLE, previous_summary.strip()))
    for day in (today - timedelta(days=1), today):
        path = daily_note_path(profile.memory_dir, day)
        body = _read_capped(path)
        if body:
            sections.append((f"memory/{path.name}", body))
    return sections


def ensure_agent_dirs(profile: AgentProfile) -> None:
    for path in (profile.dir, profile.workspace, profile.memory_dir):
        path.mkdir(parents=True, exist_ok=True)
