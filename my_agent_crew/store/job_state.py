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

    def clear(self, job_id: str) -> None:
        """Drops the override so a deleted job leaves no trace behind: a chat-created
        schedule's id is never reused, but nothing stops another one from landing at the
        exact same string, and it must not inherit a pause nobody asked it for."""
        with self._lock:
            self._conn.execute("DELETE FROM job_state WHERE job_id = ?", (job_id,))
            self._conn.commit()

    def forget_agent(self, agent_id: str) -> None:
        """Drops every switch flipped on a job of one agent's, which goes when the agent
        does: a job that an agent later made under the id states by the same name would
        start paused, or running, by a choice made for another's. A job is the agent's by
        the id and the `/` after it, read as text: `coder` takes nothing of `coder-two`,
        and an `_` in an id stands for itself, which `LIKE` would not have it do."""
        prefix = f"{agent_id}/"
        with self._lock:
            self._conn.execute(
                "DELETE FROM job_state WHERE substr(job_id, 1, ?) = ?", (len(prefix), prefix)
            )
            self._conn.commit()
