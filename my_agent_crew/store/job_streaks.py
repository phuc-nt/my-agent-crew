"""The failures in a row each job is in, kept so a restart does not begin the count again
(`scheduler/failure_streaks.py` says what a streak is and decides everything about it).

A row is a job that is failing now: how many times in a row, since when, and when the
person was last told. A job that ran well again has no row. The moments are the clock's
own, written as it gave them and read back the same."""

from __future__ import annotations

import sqlite3
import threading

# count, since, told_at: the last two as ISO texts, `told_at` None while nobody was told.
StreakRow = tuple[int, str, str | None]


class JobStreakStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def all(self) -> dict[str, StreakRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT job_id, count, since, told_at FROM job_failure_streaks"
            ).fetchall()
        return {r["job_id"]: (int(r["count"]), r["since"], r["told_at"]) for r in rows}

    def save(self, job_id: str, count: int, since: str, told_at: str | None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO job_failure_streaks (job_id, count, since, told_at)"
                " VALUES (?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET count = excluded.count,"
                " since = excluded.since, told_at = excluded.told_at",
                (job_id, count, since, told_at),
            )
            self._conn.commit()

    def clear(self, job_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM job_failure_streaks WHERE job_id = ?", (job_id,))
            self._conn.commit()

    def forget_agent(self, agent_id: str) -> None:
        """Every job of one agent's, read off the id as the switches are (`job_state.py`)."""
        prefix = f"{agent_id}/"
        with self._lock:
            self._conn.execute(
                "DELETE FROM job_failure_streaks WHERE substr(job_id, 1, ?) = ?",
                (len(prefix), prefix),
            )
            self._conn.commit()
