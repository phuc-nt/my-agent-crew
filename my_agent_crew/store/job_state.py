"""Whether a scheduled job is switched on, decided at runtime rather than in the profile.

The profile's `enabled` is the default; a row here overrides it, so a user can pause a
job from the UI without editing yaml or restarting. No row means "as the profile says"."""

from __future__ import annotations

import sqlite3
import threading


class JobStateStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def enabled(self, job_id: str) -> bool | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT enabled FROM job_state WHERE job_id = ?", (job_id,)
            ).fetchone()
        return None if row is None else bool(row["enabled"])

    def set_enabled(self, job_id: str, enabled: bool, stamp: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO job_state (job_id, enabled, updated_at) VALUES (?,?,?)"
                " ON CONFLICT(job_id) DO UPDATE SET enabled = excluded.enabled,"
                " updated_at = excluded.updated_at",
                (job_id, int(enabled), stamp),
            )
            self._conn.commit()
