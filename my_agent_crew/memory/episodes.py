"""The week's conversations, as recaps, for the nightly memory rewrite.

Daily notes hold what an agent chose to write down; what it was told and never noted is
only in the conversation. Before the rewrite, each conversation someone took part in this
week gets its recap brought up to date (`session_summary`), and the recaps join the notes
as dated entries. The rewrite then folds both into `MEMORY.md`, so a conversation that
ended without a note still reaches long-term memory, through the same gate as notes do.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from my_agent_crew import texts
from my_agent_crew.clock import local_day
from my_agent_crew.memory.session_summary import summarize_conversation

if TYPE_CHECKING:  # the loop imports memory, not the other way round
    from my_agent_crew.agent.loop import AgentDeps

logger = logging.getLogger(__name__)

EPISODE_DAYS = 7
# Recaps written per run, at most: each one is a model call over the transcript.
MAX_EPISODES = 10
# A delegated child is titled with the whole request it was handed; the heading needs less.
MAX_TITLE_CHARS = 80


@dataclass(frozen=True)
class Recalled:
    updated_at: str
    label: str
    summary: str


def memory_stamp(memory_file: Path) -> str:
    """When `MEMORY.md` was last rewritten, as a stored stamp; empty when it never was."""
    if not memory_file.is_file():
        return ""
    return datetime.fromtimestamp(memory_file.stat().st_mtime, UTC).isoformat(timespec="seconds")


async def gather_episodes(deps: AgentDeps, now: datetime | None = None) -> list[Recalled]:
    """The agent's episodes of the last week, newest first, each with a current recap. A
    recap that fails to come keeps the old one, or leaves the episode out."""
    since = ((now or datetime.now(UTC)) - timedelta(days=EPISODE_DAYS)).isoformat(
        timespec="seconds"
    )
    recalled: list[Recalled] = []
    for episode in deps.store.episodes.recent(deps.agent.id, since, MAX_EPISODES):
        summary = episode.summary
        if episode.stale:
            try:
                summary = await summarize_conversation(deps, episode.conversation_id) or summary
            except Exception:  # one recap failing must not cost the night's rewrite
                logger.exception("recap failed for conversation %s", episode.conversation_id)
        if summary:
            # The label starts with the day: the rewrite's date check accepts days it was
            # shown, and a recap is evidence for the day it was last spoken in.
            day = local_day(episode.updated_at, deps.settings.zone)
            label = texts.EPISODE_LABEL.format(day=day, title=episode.title[:MAX_TITLE_CHARS])
            recalled.append(Recalled(episode.updated_at, label, summary))
    return recalled


def has_new_episodes(recalled: list[Recalled], memory_file: Path) -> bool:
    """Someone spoke in one of them after the last rewrite."""
    stamp = memory_stamp(memory_file)
    return any(item.updated_at > stamp for item in recalled)


def merge_with_notes(
    notes: list[tuple[str, str]], recalled: list[Recalled]
) -> list[tuple[str, str]]:
    """One list, newest day first; on the same day the agent's own notes come first."""
    entries = notes + [(item.label, item.summary) for item in recalled]
    return sorted(entries, key=lambda entry: entry[0][:10], reverse=True)
