"""What the day's cap on scheduled jobs reads and keeps (`scheduler/day_cap.py`).

Read: what the runs of scheduled jobs cost since a moment, summed from the cost each run
already carries, so the cap has no meter of its own. Kept: the days the person was told the
cap was reached, one row a day, so they are told once and a restart does not tell again."""

from __future__ import annotations

import sqlite3
import threading


class JobCapStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def spent(self, source_prefix: str, since: str) -> float:
        """What the runs whose source opens with `source_prefix` and that started at
        `since` (a stored UTC stamp) or later have cost."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(spent_usd), 0) FROM runs"
                " WHERE substr(source, 1, ?) = ? AND started_at >= ?",
                (len(source_prefix), source_prefix, since),
            ).fetchone()
        return float(row[0])

    def told(self, day: str) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT 1 FROM job_cap_days WHERE day = ?", (day,)).fetchone()
        return row is not None

    def tell(self, day: str, at: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR IGNORE INTO job_cap_days (day, told_at) VALUES (?, ?)", (day, at)
            )
            self._conn.commit()
