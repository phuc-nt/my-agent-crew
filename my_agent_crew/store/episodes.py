"""Conversations as episodes: what an agent and a person went through together, recalled
by its recap rather than its transcript.

An episode is a conversation that began with a person: one they spoke in, or one an agent
was handed while answering them (a delegated child whose chain started in a chat), which is
how a specialist hears from the person at all. A scheduled job's tick and what it delegates
are left out: their output is the delivery, not a thread worth remembering, and so is a
child opened before chains recorded where they began. The recap lives in
`conversations.summary`; `summary_seq` records the last message it covered, so a thread
that carried on after its recap reads as stale. A recap written before `summary_seq`
existed has none and counts as final: it was written when the channel moved on, and
nothing is said in a replaced conversation after that.
"""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass

JOB_SOURCE_PATTERN = "job:%"
# Where a delegated chain began, as `conversations.root_source` records it: the turn
# sources a person speaks through (`agent.turn_context.PRESENT_SOURCES`).
PERSON_ROOTS = ("chat", "telegram", "api")


@dataclass(frozen=True)
class Episode:
    conversation_id: str
    title: str
    updated_at: str
    summary: str
    stale: bool


class EpisodeStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def recent(self, agent_id: str, since: str, limit: int) -> list[Episode]:
        """An agent's episodes last spoken in after `since` (a UTC stamp), newest first.
        Conversations with nothing said in them yet are left out."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT c.id, c.title, c.updated_at, c.summary, c.summary_seq,"
                " (SELECT MAX(seq) FROM messages m WHERE m.conversation_id = c.id) AS last_seq"
                " FROM conversations c WHERE c.agent_id = ?"
                " AND (c.parent_call_id = '' OR c.root_source IN (?, ?, ?))"
                " AND c.updated_at > ? AND NOT EXISTS (SELECT 1 FROM runs r"
                " WHERE r.conversation_id = c.id AND r.source LIKE ?)"
                " AND EXISTS (SELECT 1 FROM messages m WHERE m.conversation_id = c.id)"
                " ORDER BY c.updated_at DESC, c.rowid DESC LIMIT ?",
                (agent_id, *PERSON_ROOTS, since, JOB_SOURCE_PATTERN, limit),
            ).fetchall()
        return [
            Episode(
                conversation_id=row["id"],
                title=row["title"],
                updated_at=row["updated_at"],
                summary=row["summary"],
                stale=not row["summary"]
                or (row["summary_seq"] is not None and row["last_seq"] > row["summary_seq"]),
            )
            for row in rows
        ]

    def summarized_upto(self, conv_id: str) -> int | None:
        """The last message the recap covered; `None` for no recap or one older than this
        column, which callers treat as final."""
        with self._lock:
            row = self._conn.execute(
                "SELECT summary_seq FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()
        return None if row is None else row["summary_seq"]

    def mark(self, conv_id: str, seq: int) -> None:
        """Records how far the recap just written reaches. Leaves `updated_at` alone, like
        the recap itself: writing it is upkeep, not something said in the conversation."""
        with self._lock:
            self._conn.execute(
                "UPDATE conversations SET summary_seq = ? WHERE id = ?", (seq, conv_id)
            )
            self._conn.commit()
