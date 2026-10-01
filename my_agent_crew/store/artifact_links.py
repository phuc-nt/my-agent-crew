"""Which conversations know a canvas; `CanvasFocus` adds what each has open.

A link records the newest version a conversation's agent has read whole or written
(`seen_version`, 0 until it has); the note at the start of a turn diffs from there, so it
only ever moves forward. A paged read keeps a cursor beside it: the version it goes through
(`read_version`) and how many characters of it were read from the start without a gap
(`read_upto`). Only a cursor that reaches the end of its version moves `seen_version`, so
pages taken from two versions never pass for one whole read. A version some conversation has
seen or is reading is pinned: a person's next autosave adds a row instead of folding it away.
A link through which the conversation created or wrote the canvas is `shared`: the
conversation's delegated children reach the canvas through it. Sharing only ever turns
on, and reading never turns it on, so what one child read never widens the next one's reach.
A canvas note records the newest version it told the conversation about (`noted_version`):
the next note starts there, and that version is pinned as well. A note moves `seen_version`
only when it showed every change in full, and only from the version it diffed from.

Every write names a conversation and a canvas that both exist, or stores nothing, so a turn
still running after either is deleted leaves no orphan row. `commit=False` leaves a write in
the caller's transaction, so the note can mark what it showed in the same commit as the
message it is attached to."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable

from my_agent_crew.store.artifact_models import Link
from my_agent_crew.store.canvas_focus import BOTH_EXIST, CanvasFocus
from my_agent_crew.store.stamps import now_iso

_LINK = (
    "INSERT INTO conversation_artifacts (conversation_id, artifact_id, linked_at, shared)"
    f" SELECT c.id, a.id, ?, ? {BOTH_EXIST} ON CONFLICT (conversation_id, artifact_id)"
    " DO UPDATE SET shared = MAX(shared, excluded.shared)"
)
_MARK_SEEN = (
    "INSERT INTO conversation_artifacts (conversation_id, artifact_id, seen_version, linked_at)"
    f" SELECT c.id, a.id, ?, ? {BOTH_EXIST} ON CONFLICT (conversation_id, artifact_id)"
    " DO UPDATE SET seen_version = MAX(seen_version, excluded.seen_version) RETURNING *"
)
_MARK_NOTED = (
    "UPDATE conversation_artifacts SET noted_version = MAX(noted_version, ?)"
    " WHERE conversation_id = ? AND artifact_id = ?"
)
_ADVANCE_SEEN = (
    "UPDATE conversation_artifacts SET seen_version = ? WHERE conversation_id = ?"
    " AND artifact_id = ? AND seen_version = ? AND seen_version < ?"
)
_SET_READ = (
    "UPDATE conversation_artifacts SET read_version = ?, read_upto = ?, seen_version = ?"
    " WHERE conversation_id = ? AND artifact_id = ? RETURNING *"
)


class ArtifactLinks(CanvasFocus):
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

    def _ensure(self, conversation_id: str, artifact_id: str, shared: bool = False) -> Link | None:
        self._conn.execute(_LINK, (now_iso(), int(shared), conversation_id, artifact_id))
        return self.get(conversation_id, artifact_id)

    def get(self, conversation_id: str, artifact_id: str) -> Link | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM conversation_artifacts WHERE conversation_id = ?"
                " AND artifact_id = ?",
                (conversation_id, artifact_id),
            ).fetchone()
        return None if row is None else Link.from_row(row)

    def link(
        self, conversation_id: str, artifact_id: str, *, shared: bool = False, commit: bool = True
    ) -> Link | None:
        """Links the two once; linking again keeps what the conversation has seen and read,
        and shares the link if it was not yet. None when either is missing."""
        return self._write(lambda: self._ensure(conversation_id, artifact_id, shared), commit)

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

    def mark_noted(
        self, conversation_id: str, artifact_id: str, version: int, *, commit: bool = True
    ) -> None:
        """Records that a note told of `version`. Never moves back, never makes a link."""
        params = (version, conversation_id, artifact_id)
        self._write(lambda: self._conn.execute(_MARK_NOTED, params), commit)

    def advance_seen(
        self, conversation_id: str, artifact_id: str, base: int, head: int, *, commit: bool = True
    ) -> bool:
        """Moves `seen_version` from exactly `base` up to `head`. False, moving nothing, when
        a read or a write moved it meanwhile or the link is missing."""
        params = (head, conversation_id, artifact_id, base, head)
        return self._write(lambda: self._conn.execute(_ADVANCE_SEEN, params).rowcount > 0, commit)

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
        """Whether some conversation's agent has seen this version or a later one, was told
        of one by a note, or is reading one page by page: its next note diffs from that
        version and its next page is cut from it, so the version must not be folded away."""
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM conversation_artifacts WHERE artifact_id = ?"
                " AND MAX(seen_version, read_version, noted_version) >= ? LIMIT 1",
                (artifact_id, version),
            ).fetchone()
        return row is not None
