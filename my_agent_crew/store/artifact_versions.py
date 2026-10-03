"""How a canvas gains versions. Every write adds a full copy under the next number, and a
number is never used twice, so a tab still holding an old one always learns it is behind.

A person's autosaves fold into one row while they belong to one burst: the newest row and
the new write are both the person's, neither carries a note, the burst began at most
COALESCE_WINDOW_S ago, and the newest row is not pinned (`ArtifactLinks.pinned`). Folding
deletes that row and adds the next number with the burst's first `created_at`, so a burst
closes a window after its first save however long the typing goes on. A version an agent
wrote, saw or is reading page by page is never folded away: the turn's note diffs from it
and the next page is cut from it, so it must still be there."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from my_agent_crew.artifacts.kinds import clean_title, prepare
from my_agent_crew.store.artifact_history import META_COLUMNS, ArtifactHistory
from my_agent_crew.store.artifact_models import (
    RESTORE_NOTE,
    USER,
    ArtifactSummary,
    ArtifactVersion,
    VersionConflict,
)
from my_agent_crew.store.stamps import now_iso

if TYPE_CHECKING:
    from my_agent_crew.store.artifact_links import ArtifactLinks

COALESCE_WINDOW_S = 120
_INSERT = (
    f"INSERT INTO artifact_versions ({META_COLUMNS}, content, data)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING *"
)
_ADVANCE = (
    "UPDATE artifacts SET head_version = ?, updated_at = ?, title = COALESCE(?, title)"
    " WHERE id = ? RETURNING *"
)

# What a write puts in the next version, given the newest one: (content, data).
Payload = Callable[[ArtifactVersion], tuple[str | None, bytes | None]]


class ArtifactVersions(ArtifactHistory):
    """Adding versions, on top of reading them; mixed into `ArtifactStore`, which supplies
    `get`, `_check_write` and `_notify`."""

    _conn: sqlite3.Connection
    _lock: threading.RLock
    _links: ArtifactLinks

    def write(
        self,
        artifact_id: str,
        content: str | None,
        author: str,
        conversation_id: str,
        base_version: int | None = None,
        title: str | None = None,
        note: str = "",
        *,
        data: bytes | None = None,
    ) -> ArtifactVersion:
        """With `base_version`, refuses unless that is still the newest version, so an editor
        that loaded an older one cannot write over what came since."""

        def payload(head: ArtifactVersion) -> tuple[str | None, bytes | None]:
            if base_version is not None and base_version != head.version:
                raise VersionConflict(head.version, head.content)
            return content, data

        return self._write_next(artifact_id, payload, author, conversation_id, title, note)

    def apply(
        self,
        artifact_id: str,
        change: Callable[[ArtifactVersion], str],
        author: str,
        conversation_id: str,
        title: str | None = None,
        note: str = "",
    ) -> ArtifactVersion:
        """Hands `change` the newest version and writes the text it returns, in one step: no
        other write lands in between, and when `change` raises nothing is written. It runs
        with the store's lock held, so every other read and write waits for it: keep it a
        quick, plain transformation, with no fuzzy search and no I/O."""

        def payload(head: ArtifactVersion) -> tuple[str | None, bytes | None]:
            return change(head), None

        return self._write_next(artifact_id, payload, author, conversation_id, title, note)

    def restore(
        self, artifact_id: str, version: int, author: str, conversation_id: str
    ) -> ArtifactVersion:
        """Writes an old version's payload as the newest; the versions after it stay."""

        def payload(head: ArtifactVersion) -> tuple[str | None, bytes | None]:
            old = self.version(artifact_id, version)
            return old.content, old.data

        note = f"{RESTORE_NOTE}{version}"
        return self._write_next(artifact_id, payload, author, conversation_id, None, note)

    def _insert_version(self, *values: object) -> sqlite3.Row:
        """One version row: the `META_COLUMNS` in order, then content and data."""
        [row] = self._conn.execute(_INSERT, values).fetchall()
        return row

    def _folds_into(self, head: ArtifactVersion, author: str, note: str, now: str) -> bool:
        began = datetime.fromisoformat(head.created_at)
        elapsed = (datetime.fromisoformat(now) - began).total_seconds()
        return (
            author == USER == head.author
            and not note
            and not head.note
            and 0 <= elapsed <= COALESCE_WINDOW_S
            and not self._links.pinned(head.artifact_id, head.version)
        )

    def _write_next(
        self,
        artifact_id: str,
        payload: Payload,
        author: str,
        conversation_id: str,
        title: str | None,
        note: str,
    ) -> ArtifactVersion:
        """Adds the version after the newest, folding the newest away when this write
        continues its burst. One hold of the lock covers the first read to the commit, a
        failure anywhere rolls back all of it, and listeners hear of the change only once
        it is committed and the lock is released."""
        title = None if title is None else clean_title(title)
        with self._lock:
            kind = self.get(artifact_id).kind
            head = self.head(artifact_id)
            content, data = payload(head)
            content, size = prepare(kind, content, data)
            now = now_iso()
            folds = self._folds_into(head, author, note, now)
            self._check_write(author, size - (head.size if folds else 0))
            number = head.version + 1
            meta = (artifact_id, number, size, author, conversation_id, note)
            stamps = (head.created_at if folds else now, now)
            try:
                if folds:
                    self._conn.execute(
                        "DELETE FROM artifact_versions WHERE artifact_id = ? AND version = ?",
                        (artifact_id, head.version),
                    )
                row = self._insert_version(*meta, *stamps, content, data)
                advance = (number, now, title, artifact_id)
                [summary] = self._conn.execute(_ADVANCE, advance).fetchall()
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise
            linked = self._links.conversations_for(artifact_id)
        self._notify(ArtifactSummary.from_row(summary).to_dict(), linked)
        return ArtifactVersion.from_row(row)
