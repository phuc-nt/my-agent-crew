"""The hosts the process called, as calls per host per day (`my_agent_crew/egress.py`).

A row is a day, a host name and a number. The host is cleaned again on its way in, so
whatever a caller hands over, nothing but a host name lands in the table. Rows older than
`KEEP_DAYS` leave with each write."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

from my_agent_crew.egress import clean_host

KEEP_DAYS = 90


class EgressStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def add(self, counts: Mapping[tuple[str, str], int], today: str) -> None:
        """Adds `counts` ((day, host) -> calls) to what is kept and drops the rows more
        than `KEEP_DAYS` days before `today`. All of it or none of it."""
        oldest = (date.fromisoformat(today) - timedelta(days=KEEP_DAYS)).isoformat()
        rows = [
            (date.fromisoformat(d).isoformat(), clean_host(h), int(n))
            for (d, h), n in counts.items()
        ]
        with self._lock:
            try:
                self._conn.executemany(
                    "INSERT INTO egress_hosts (day, host, calls) VALUES (?, ?, ?)"
                    " ON CONFLICT (day, host) DO UPDATE SET calls = calls + excluded.calls",
                    rows,
                )
                self._conn.execute("DELETE FROM egress_hosts WHERE day < ?", (oldest,))
                self._conn.commit()
            except sqlite3.Error:
                self._conn.rollback()
                raise

    def since(self, day: str) -> list[dict[str, Any]]:
        """Each host called on `day` or later: its calls, on how many days, and the last
        of them. Most called first, then by name."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT host, SUM(calls) AS calls, COUNT(*) AS days, MAX(day) AS last_day"
                " FROM egress_hosts WHERE day >= ? GROUP BY host ORDER BY calls DESC, host",
                (day,),
            ).fetchall()
        return [dict(row) for row in rows]

    def rows_since(self, day: str) -> list[dict[str, Any]]:
        """The same rows unsummed, one per day and host, oldest day first: for a reader that
        keeps a copy and has to tell one day's count from the next."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT day, host, calls FROM egress_hosts WHERE day >= ? ORDER BY day, host",
                (day,),
            ).fetchall()
        return [dict(row) for row in rows]
