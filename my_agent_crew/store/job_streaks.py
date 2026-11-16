"""The failures in a row each job is in, kept so a restart does not begin the count again
(`scheduler/failure_streaks.py` says what a streak is and decides everything about it).

A row is a job that is failing now: how many times in a row, and since when. A job that
ran well again has no row. The moment is the clock's own, written as it gave it and read
back the same. A home made before streaks were told to no channel keeps a `told_at`
column here, which nothing reads or writes any more."""

from __future__ import annotations

import sqlite3
import threading

# count, and since as an ISO text.
StreakRow = tuple[int, str]


class JobStreakStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def all(self) -> dict[str, StreakRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT job_id, count, since FROM job_failure_streaks"
            ).fetchall()
        return {r["job_id"]: (int(r["count"]), r["since"]) for r in rows}

    def save(self, job_id: str, count: int, since: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO job_failure_streaks (job_id, count, since) VALUES (?,?,?)"
                " ON CONFLICT(job_id) DO UPDATE SET count = excluded.count,"
                " since = excluded.since",
                (job_id, count, since),
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
