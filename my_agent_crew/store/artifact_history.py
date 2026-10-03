"""Reading a canvas's versions: the newest, one by its number, and the whole history without
payloads. A number is never used twice, so a version a later save folded away stays gone and
`version` says so, with the number of the newest one."""

from __future__ import annotations

import sqlite3
import threading

from my_agent_crew.store.artifact_models import ArtifactVersion, VersionGone

META_COLUMNS = "artifact_id, version, size, author, conversation_id, note, created_at, updated_at"


def fits_sqlite(number: int) -> bool:
    """Whether the driver can bind `number`: SQLite keeps an INTEGER in 64 bits and the driver
    refuses a Python int beyond them with an OverflowError. No version row can hold such a
    number, so asking for one is asking for a version that is not there."""
    return -(2**63) <= number < 2**63


class ArtifactHistory:
    """Reading versions; mixed into `ArtifactStore`, which supplies `get`."""

    _conn: sqlite3.Connection
    _lock: threading.RLock

    def head(self, artifact_id: str) -> ArtifactVersion:
        with self._lock:
            row = self._conn.execute(
                "SELECT v.* FROM artifact_versions v JOIN artifacts a"
                " ON v.artifact_id = a.id AND v.version = a.head_version WHERE a.id = ?",
                (artifact_id,),
            ).fetchone()
        if row is None:
            raise KeyError(artifact_id)
        return ArtifactVersion.from_row(row)

    def version(self, artifact_id: str, version: int) -> ArtifactVersion:
        """`VersionGone` when the canvas is there without this version, else KeyError. Every
        version a caller names comes through here, so a number the database cannot hold is
        turned away here as the version that is not there, instead of failing in the driver."""
        with self._lock:
            row = None
            if fits_sqlite(version):
                row = self._conn.execute(
                    "SELECT * FROM artifact_versions WHERE artifact_id = ? AND version = ?",
                    (artifact_id, version),
                ).fetchone()
            if row is None:
                raise VersionGone(artifact_id, version, self.get(artifact_id).head_version)
        return ArtifactVersion.from_row(row)

    def versions(self, artifact_id: str) -> list[ArtifactVersion]:
        """The history, oldest first, without payloads. Every canvas has at least one
        version, so none at all means there is no such canvas."""
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {META_COLUMNS} FROM artifact_versions WHERE artifact_id = ?"
                " ORDER BY version",
                (artifact_id,),
            ).fetchall()
        if not rows:
            raise KeyError(artifact_id)
        return [ArtifactVersion.from_row(row) for row in rows]
