"""What the day's cap on scheduled jobs reads (`scheduler/day_cap.py`): what the runs of
scheduled jobs cost since a moment, summed from the cost each run already carries, so the
cap has no meter of its own."""

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
