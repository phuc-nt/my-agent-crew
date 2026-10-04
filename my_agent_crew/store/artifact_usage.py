"""What the canvases add up to: the bytes each one keeps, counted across every version of it,
since an old version is never pruned and takes its room for as long as the canvas lives; and
the canvases an agent wrote in one conversation, which is what a delegation hands back."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass

# Only an agent's versions: a person may open the same conversation and save there, and that
# is not the agent's work. In the order each canvas was first written, by rowid, since two
# writes may share a timestamp and an agent's row, never folded away, keeps the rowid it got.
_WRITTEN = (
    "SELECT v.artifact_id, MAX(v.version), a.title"
    " FROM artifact_versions v JOIN artifacts a ON a.id = v.artifact_id"
    " WHERE v.conversation_id = ? AND v.author LIKE 'agent:%'"
    " GROUP BY v.artifact_id ORDER BY MIN(v.rowid)"
)


@dataclass(frozen=True)
class Written:
    """A canvas an agent wrote in a conversation: the newest version an agent wrote there,
    which a person's later save may have left behind, and the title the canvas has now."""

    id: str
    version: int
    title: str


class ArtifactUsage:
    """Mixed into `ArtifactStore`."""

    _conn: sqlite3.Connection
    _lock: threading.RLock

    def sizes(self) -> dict[str, int]:
        """Bytes each canvas keeps across all its versions."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT artifact_id, SUM(size) FROM artifact_versions GROUP BY artifact_id"
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    def written_in(self, conversation_id: str) -> list[Written]:
        """The canvases an agent added a version to from `conversation_id`, whether it began
        them, changed them or imported a file into them. What adds no version is not there:
        an export, an import that changed nothing, a new title. Neither is a deleted canvas,
        whose versions went with it."""
        with self._lock:
            rows = self._conn.execute(_WRITTEN, (conversation_id,)).fetchall()
        return [Written(*row) for row in rows]
