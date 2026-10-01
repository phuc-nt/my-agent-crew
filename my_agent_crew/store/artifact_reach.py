"""Which canvases an agent other than the master reaches from a conversation: those linked to
the conversation, those the root of its delegation shares, and those the agent created.

A person's canvas is filed under agent "", which no agent id can be, so only a link reaches
it. Reading a canvas links only the conversation that read it, never the root, and a link a
read made is never shared, so what one delegated child read never widens what the next one
reaches."""

from __future__ import annotations

import sqlite3
import threading
from itertools import islice
from typing import Any

from my_agent_crew.memory.search import normalize
from my_agent_crew.store.artifact_models import ArtifactSummary

# Part of the query, so canvases out of reach never use up the limit. A root of "" is no
# conversation, so a conversation that opened no chain reaches through its own links only.
_SCOPE = (
    "(a.id IN (SELECT artifact_id FROM conversation_artifacts"
    " WHERE conversation_id = :conv OR (conversation_id = :root AND shared = 1))"
    " OR a.agent_id = :agent)"
)
NEWEST_FIRST = " ORDER BY a.updated_at DESC, a.rowid DESC"


class ArtifactReach:
    """Mixed into `ArtifactStore`."""

    _conn: sqlite3.Connection
    _lock: threading.RLock

    def reachable(
        self,
        conversation_id: str,
        root_id: str,
        agent_id: str,
        query: str | None = None,
        limit: int = 30,
    ) -> list[ArtifactSummary]:
        """Most recently changed first; `query` matches the title as `list` matches it."""
        sql = f"SELECT a.* FROM artifacts a WHERE {_SCOPE}{NEWEST_FIRST}"
        return self._titled(sql, _scope(conversation_id, root_id, agent_id), query, limit)

    def is_reachable(
        self, artifact_id: str, conversation_id: str, root_id: str, agent_id: str
    ) -> bool:
        params = {**_scope(conversation_id, root_id, agent_id), "id": artifact_id}
        with self._lock:
            row = self._conn.execute(
                f"SELECT 1 FROM artifacts a WHERE a.id = :id AND {_SCOPE}", params
            ).fetchone()
        return row is not None

    def _titled(
        self, sql: str, params: dict[str, Any], query: str | None, limit: int
    ) -> list[ArtifactSummary]:
        """The rows `sql` selects and orders, keeping those whose title holds `query`
        regardless of case and accents. SQLite's LIKE cannot match that beyond ASCII, so the
        title is matched here, and the limit goes into the SQL only when there is no query."""
        needle = normalize(query.strip()) if query else ""
        if not needle:
            sql, params = f"{sql} LIMIT :limit", {**params, "limit": limit}
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        found = (ArtifactSummary.from_row(row) for row in rows)
        if needle:
            found = (summary for summary in found if needle in normalize(summary.title))
        return [*islice(found, limit)]


def _scope(conversation_id: str, root_id: str, agent_id: str) -> dict[str, str]:
    """An agent id of "" would match every canvas a person made, so it is refused."""
    if not agent_id:
        raise ValueError("an agent's reach needs the agent's id")
    return {"conv": conversation_id, "root": root_id, "agent": agent_id}
