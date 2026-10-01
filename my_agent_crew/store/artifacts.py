"""Canvases: documents an agent or a person writes beside a conversation, each kept as a
chain of full versions (`artifact_versions.py`). The store checks every payload against its
kind (`artifacts/kinds.py`), so a tool, a route and an import meet the same limits.

`on_change` hears every committed change with the canvas's summary, or `{"id", "deleted"}`,
and the conversations linked to it at that moment. It runs after the commit with the lock
released, so a listener may read the store back; a listener that fails is logged and never
undoes the write it was told about."""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Callable
from typing import Any

from my_agent_crew.agent_ids import is_agent_id
from my_agent_crew.artifacts.kinds import (
    STORAGE_CAP,
    StorageFull,
    clean_language,
    clean_title,
    prepare,
)
from my_agent_crew.store.artifact_links import ArtifactLinks
from my_agent_crew.store.artifact_models import USER, ArtifactSummary
from my_agent_crew.store.artifact_reach import NEWEST_FIRST, ArtifactReach
from my_agent_crew.store.artifact_versions import ArtifactVersions
from my_agent_crew.store.stamps import new_id, now_iso

logger = logging.getLogger(__name__)

# Rows that belong to one canvas and go with it.
_OWNED = ("artifact_versions", "conversation_artifacts", "canvas_focus")


class ArtifactStore(ArtifactReach, ArtifactVersions):
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock, links: ArtifactLinks):
        self._conn = conn
        self._lock = lock
        self._links = links
        self.on_change: Callable[[dict[str, Any], list[str]], None] | None = None

    def create(
        self,
        title: str,
        kind: str,
        agent_id: str,
        author: str,
        conversation_id: str,
        content: str | None = None,
        data: bytes | None = None,
        language: str = "",
        source: str = "",
    ) -> ArtifactSummary:
        """A new canvas at version 1. It is linked to no conversation yet: whoever creates
        it links it, so the change it announces lists no conversations. `agent_id` names the
        creator and must match `author`: "" for the person, "<id>" for "agent:<id>"."""
        creator = USER if agent_id == "" else f"agent:{agent_id}"
        if author != creator:
            raise ValueError(f"author {author!r} did not create a canvas filed under {creator!r}")
        title, language = clean_title(title), clean_language(language)
        content, size = prepare(kind, content, data)
        artifact_id, now = new_id(), now_iso()
        with self._lock:
            self._check_write(author, size)
            try:
                [row] = self._conn.execute(
                    "INSERT INTO artifacts (id, title, kind, language, agent_id, head_version,"
                    " source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)"
                    " RETURNING *",
                    (artifact_id, title, kind, language, agent_id, source, now, now),
                ).fetchall()
                meta = (artifact_id, 1, size, author, conversation_id, "")
                self._insert_version(*meta, now, now, content, data)
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise
        summary = ArtifactSummary.from_row(row)
        self._notify(summary.to_dict(), [])
        return summary

    def get(self, artifact_id: str) -> ArtifactSummary:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM artifacts WHERE id = ?", (artifact_id,)
            ).fetchone()
        if row is None:
            raise KeyError(artifact_id)
        return ArtifactSummary.from_row(row)

    def list(
        self,
        conversation_id: str | None = None,
        agent_id: str | None = None,
        query: str | None = None,
        limit: int = 50,
    ) -> list[ArtifactSummary]:
        """Most recently changed first; `query` matches the title regardless of case and
        accents (`ArtifactReach._titled`)."""
        sql, where, params = "SELECT a.* FROM artifacts a", [], {}
        if conversation_id is not None:
            sql += " JOIN conversation_artifacts l ON l.artifact_id = a.id"
            where.append("l.conversation_id = :conv")
            params["conv"] = conversation_id
        if agent_id is not None:
            where.append("a.agent_id = :agent")
            params["agent"] = agent_id
        if where:
            sql += " WHERE " + " AND ".join(where)
        return self._titled(sql + NEWEST_FIRST, params, query, limit)

    def rename(self, artifact_id: str, title: str) -> ArtifactSummary:
        """A new title only: no new version."""
        title = clean_title(title)
        with self._lock:
            rows = self._conn.execute(
                "UPDATE artifacts SET title = ?, updated_at = ? WHERE id = ? RETURNING *",
                (title, now_iso(), artifact_id),
            ).fetchall()
            self._conn.commit()
            linked = self._links.conversations_for(artifact_id)
        if not rows:
            raise KeyError(artifact_id)
        summary = ArtifactSummary.from_row(rows[0])
        self._notify(summary.to_dict(), linked)
        return summary

    def delete(self, artifact_id: str) -> None:
        """The canvas with every version, link and open panel of it. Conversations stay."""
        with self._lock:
            linked = self._links.conversations_for(artifact_id)
            try:
                for table in _OWNED:
                    self._conn.execute(f"DELETE FROM {table} WHERE artifact_id = ?", (artifact_id,))
                cur = self._conn.execute("DELETE FROM artifacts WHERE id = ?", (artifact_id,))
                if cur.rowcount == 0:
                    raise KeyError(artifact_id)
                self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise
        self._notify({"id": artifact_id, "deleted": True}, linked)

    def sizes(self) -> dict[str, int]:
        """Bytes each canvas keeps across all its versions."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT artifact_id, SUM(size) FROM artifact_versions GROUP BY artifact_id"
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def _check_write(self, author: str, added: int) -> None:
        """Refuses an author that is neither the person nor a named agent, and a write that
        would take every canvas together past its author's ceiling: STORAGE_CAP for the
        person, a tenth short of it for an agent, so a writer stuck in a loop still leaves the
        person room to save. Called with the lock held, so two writers cannot both fit under
        the ceiling with the same last bytes."""
        named_agent = author.startswith("agent:") and is_agent_id(author.removeprefix("agent:"))
        if author != USER and not named_agent:
            raise ValueError(f"author must be {USER!r} or 'agent:<id>', not {author!r}")
        cap = STORAGE_CAP if author == USER else STORAGE_CAP * 9 // 10
        [used] = self._conn.execute(
            "SELECT COALESCE(SUM(size), 0) FROM artifact_versions"
        ).fetchone()
        if used + added > cap:
            raise StorageFull(used, cap)

    def _notify(self, summary: dict[str, Any], conversation_ids: list[str]) -> None:
        if self.on_change is None:
            return
        try:
            self.on_change(summary, conversation_ids)
        except Exception:
            logger.exception("a listener failed on the change to canvas %s", summary["id"])
