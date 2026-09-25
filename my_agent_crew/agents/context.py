"""What an agent reads at the start of every turn: its persona files, its long-term
memory file and the daily notes for today and yesterday. Files are re-read each turn so
an edit on disk takes effect on the next message, no restart."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

from my_agent_crew.agents.kit import split_front_matter
from my_agent_crew.agents.profile import AgentProfile
from my_agent_crew.memory import user_store
from my_agent_crew.memory.wiki_index import wiki_section
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


def _persona(path: Path) -> str | None:
    """A persona file's text; a kit's agent markdown carries a front matter the model
    need not read, so only the body is kept."""
    text = _read_capped(path)
    if text and text.startswith("---"):
        _, text = split_front_matter(text)
    return text or None


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
    previous_at: str = "",
    extra_sections: Sequence[tuple[str, str]] = (),
) -> list[tuple[str, str]]:
    """(title, body) pairs in the order they enter the system prompt.

    `extra_sections` are context the caller assembled for this turn alone; they sit after
    what the agent carries between turns and before today's notes.
    """
    today = today or date.today()
    sections: list[tuple[str, str]] = []
    for name in profile.persona_files:
        body = _persona(profile.dir / name)
        if body:
            # A kit file is named by its absolute path; the section reads by its file name.
            sections.append((Path(name).name if Path(name).is_absolute() else name, body))
    sections.extend(user_sections(profile.settings.user_dir))
    memory = _read_capped(profile.memory_file)
    if memory:
        sections.append(("MEMORY.md", memory))
    # After the durable memory file and before today's notes: the vault is settled
    # knowledge, so it should be read in the same frame of mind and not mistaken for
    # something that happened today.
    wiki = wiki_section(profile.memory_dir)
    if wiki:
        sections.append(wiki)
    if previous_summary.strip():
        title = PREVIOUS_SUMMARY_SECTION_TITLE.format(when=previous_at or "?")
        sections.append((title, previous_summary.strip()))
    sections.extend(extra_sections)
    for day in (today - timedelta(days=1), today):
        path = daily_note_path(profile.memory_dir, day)
        body = _read_capped(path)
        if body:
            sections.append((f"memory/{path.name}", body))
    return sections


def ensure_agent_dirs(profile: AgentProfile) -> None:
    for path in (profile.dir, profile.workspace, profile.memory_dir):
        path.mkdir(parents=True, exist_ok=True)
