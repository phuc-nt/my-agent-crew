"""Which conversations know a canvas, and what each has open.

A link records the newest version a conversation's agent has read or written
(`seen_version`, 0 until it has); the note at the start of a turn diffs from there, so it
only ever moves forward. A focus is web UI state: the canvas a conversation has open and
the passage the person selected in it, which the next turn's note quotes once and clears.

`commit=False` leaves a write in the caller's transaction, so the note can mark what it
showed in the same commit as the message it is attached to."""

from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any

from my_agent_crew.store.artifact_models import Focus, Link
from my_agent_crew.store.stamps import now_iso

_MARK_SEEN = (
    "INSERT INTO conversation_artifacts (conversation_id, artifact_id, seen_version, linked_at)"
    " VALUES (?, ?, ?, ?) ON CONFLICT (conversation_id, artifact_id)"
    " DO UPDATE SET seen_version = MAX(seen_version, excluded.seen_version)"
)
_SET_FOCUS = (
    "INSERT INTO canvas_focus (conversation_id, artifact_id, selection, updated_at)"
    " VALUES (?, ?, ?, ?) ON CONFLICT (conversation_id) DO UPDATE SET"
    " artifact_id = excluded.artifact_id, selection = excluded.selection,"
    " updated_at = excluded.updated_at"
)


class ArtifactLinks:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def _write(self, sql: str, params: tuple, commit: bool) -> None:
        with self._lock:
            self._conn.execute(sql, params)
            if commit:
                self._conn.commit()

    def link(self, conversation_id: str, artifact_id: str, *, commit: bool = True) -> None:
        """Links the two once; linking again keeps what the conversation has seen."""
        sql = (
            "INSERT OR IGNORE INTO conversation_artifacts"
            " (conversation_id, artifact_id, seen_version, linked_at) VALUES (?, ?, 0, ?)"
        )
        self._write(sql, (conversation_id, artifact_id, now_iso()), commit)

    def mark_seen(
        self, conversation_id: str, artifact_id: str, version: int, *, commit: bool = True
    ) -> None:
        """Links them if they were not, and never moves `seen_version` back."""
        self._write(_MARK_SEEN, (conversation_id, artifact_id, version, now_iso()), commit)

    def links_for(self, conversation_id: str) -> list[Link]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM conversation_artifacts WHERE conversation_id = ? ORDER BY rowid",
                (conversation_id,),
            ).fetchall()
        return [Link.from_row(row) for row in rows]

    def conversations_for(self, artifact_id: str) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT conversation_id FROM conversation_artifacts WHERE artifact_id = ?"
                " ORDER BY rowid",
                (artifact_id,),
            ).fetchall()
        return [row[0] for row in rows]

    def any_seen(self, artifact_id: str, version: int) -> bool:
        """Whether some conversation's agent has seen this version or a later one."""
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM conversation_artifacts WHERE artifact_id = ? AND seen_version >= ?"
                " LIMIT 1",
                (artifact_id, version),
            ).fetchone()
        return row is not None

    def focus(self, conversation_id: str) -> Focus | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM canvas_focus WHERE conversation_id = ?", (conversation_id,)
            ).fetchone()
        return None if row is None else Focus.from_row(row)

    def set_focus(
        self, conversation_id: str, artifact_id: str, selection: dict[str, Any] | None
    ) -> None:
        stored = "" if selection is None else json.dumps(selection, ensure_ascii=False)
        self._write(_SET_FOCUS, (conversation_id, artifact_id, stored, now_iso()), True)

    def clear_selection(self, conversation_id: str, *, commit: bool = True) -> None:
        sql = "UPDATE canvas_focus SET selection = '', updated_at = ? WHERE conversation_id = ?"
        self._write(sql, (now_iso(), conversation_id), commit)

    def clear_focus(self, conversation_id: str) -> None:
        self._write("DELETE FROM canvas_focus WHERE conversation_id = ?", (conversation_id,), True)
