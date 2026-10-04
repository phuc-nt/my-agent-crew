"""What the canvases add up to: the bytes each one keeps, counted across every version of it,
since an old version is never pruned and takes its room for as long as the canvas lives."""

from __future__ import annotations

import sqlite3
import threading


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
