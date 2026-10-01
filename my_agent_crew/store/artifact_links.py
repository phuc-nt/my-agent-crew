"""Which conversations know a canvas, and what each has open.

A link records the newest version a conversation's agent has read whole or written
(`seen_version`, 0 until it has); the note at the start of a turn diffs from there, so it
only ever moves forward. A paged read keeps a cursor beside it: the version it goes through
(`read_version`) and how many characters of it were read from the start without a gap
(`read_upto`). Only a cursor that reaches the end of its version moves `seen_version`, so
pages taken from two versions never pass for one whole read. A version some conversation has
seen or is reading is pinned: a person's next autosave adds a row instead of folding it away.

A focus is web UI state: the canvas a conversation has open and the passage the person
selected in it, which the next turn's note quotes once and clears.

Every write names a conversation and a canvas that both exist, or stores nothing, so a turn
still running after either is deleted leaves no orphan row. `commit=False` leaves a write in
the caller's transaction, so the note can mark what it showed in the same commit as the
message it is attached to."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable
from typing import Any

from my_agent_crew.store.artifact_models import Focus, Link
from my_agent_crew.store.stamps import now_iso

# Selects the pair only while both rows exist; an insert from it stores nothing otherwise.
# The WHERE also keeps SQLite from reading the upsert's ON as a join's.
_BOTH = "FROM conversations c, artifacts a WHERE c.id = ? AND a.id = ?"
_LINK = (
    "INSERT INTO conversation_artifacts (conversation_id, artifact_id, linked_at)"
    f" SELECT c.id, a.id, ? {_BOTH} ON CONFLICT (conversation_id, artifact_id) DO NOTHING"
)
_MARK_SEEN = (
    "INSERT INTO conversation_artifacts (conversation_id, artifact_id, seen_version, linked_at)"
    f" SELECT c.id, a.id, ?, ? {_BOTH} ON CONFLICT (conversation_id, artifact_id)"
    " DO UPDATE SET seen_version = MAX(seen_version, excluded.seen_version) RETURNING *"
)
_SET_READ = (
    "UPDATE conversation_artifacts SET read_version = ?, read_upto = ?, seen_version = ?"
    " WHERE conversation_id = ? AND artifact_id = ? RETURNING *"
)
_SET_FOCUS = (
    "INSERT INTO canvas_focus (conversation_id, artifact_id, selection, updated_at)"
    f" SELECT c.id, a.id, ?, ? {_BOTH} ON CONFLICT (conversation_id) DO UPDATE SET"
    " artifact_id = excluded.artifact_id, selection = excluded.selection,"
    " updated_at = excluded.updated_at"
)


class ArtifactLinks:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def _write[T](self, step: Callable[[], T], commit: bool) -> T:
        """Runs `step` under the lock; with `commit`, commits it or rolls all of it back."""
        with self._lock:
            try:
                result = step()
                if commit:
                    self._conn.commit()
            except BaseException:
                if commit:
                    self._conn.rollback()
                raise
        return result

    def _ensure(self, conversation_id: str, artifact_id: str) -> Link | None:
        self._conn.execute(_LINK, (now_iso(), conversation_id, artifact_id))
        row = self._conn.execute(
            "SELECT * FROM conversation_artifacts WHERE conversation_id = ? AND artifact_id = ?",
            (conversation_id, artifact_id),
        ).fetchone()
        return None if row is None else Link.from_row(row)

    def link(self, conversation_id: str, artifact_id: str, *, commit: bool = True) -> Link | None:
        """Links the two once; linking again keeps what the conversation has seen and read.
        None when either is missing."""
        return self._write(lambda: self._ensure(conversation_id, artifact_id), commit)

    def mark_seen(
        self, conversation_id: str, artifact_id: str, version: int, *, commit: bool = True
    ) -> Link | None:
        """Links them if they were not, and never moves `seen_version` back."""
        params = (version, now_iso(), conversation_id, artifact_id)
        rows = self._write(lambda: self._conn.execute(_MARK_SEEN, params).fetchall(), commit)
        return Link.from_row(rows[0]) if rows else None

    def mark_read(
        self,
        conversation_id: str,
        artifact_id: str,
        version: int,
        start: int,
        end: int,
        total: int,
        *,
        commit: bool = True,
    ) -> Link | None:
        """Records a page holding characters `start` to `end` of the `total` in `version`. A
        page from the start of a newer version begins the cursor again, a page that begins
        inside what was read extends it, and any other page moves nothing. A cursor that
        reaches the end of its version makes that version seen."""

        def step() -> Link | None:
            link = self._ensure(conversation_id, artifact_id)
            if link is None:
                return None
            read_version, upto = link.read_version, link.read_upto
            if start == 0 and version > read_version:
                read_version, upto = version, end
            elif version == read_version and start <= upto:
                upto = max(upto, end)
            seen = link.seen_version
            if read_version == version and upto >= total:
                seen = max(seen, version)
            params = (read_version, upto, seen, conversation_id, artifact_id)
            [row] = self._conn.execute(_SET_READ, params).fetchall()
            return Link.from_row(row)

        return self._write(step, commit)

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

    def pinned(self, artifact_id: str, version: int) -> bool:
        """Whether some conversation's agent has seen this version or a later one, or is
        reading one page by page: its next note diffs from that version and its next page
        is cut from it, so the version must not be folded away."""
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM conversation_artifacts WHERE artifact_id = ?"
                " AND MAX(seen_version, read_version) >= ? LIMIT 1",
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
    ) -> bool:
        """False, with nothing stored, when either is missing."""
        stored = "" if selection is None else json.dumps(selection, ensure_ascii=False)
        params = (stored, now_iso(), conversation_id, artifact_id)
        return self._write(lambda: self._conn.execute(_SET_FOCUS, params).rowcount > 0, True)

    def clear_selection(self, conversation_id: str, *, commit: bool = True) -> None:
        sql = "UPDATE canvas_focus SET selection = '', updated_at = ? WHERE conversation_id = ?"
        self._write(lambda: self._conn.execute(sql, (now_iso(), conversation_id)), commit)

    def clear_focus(self, conversation_id: str) -> None:
        sql = "DELETE FROM canvas_focus WHERE conversation_id = ?"
        self._write(lambda: self._conn.execute(sql, (conversation_id,)), True)
