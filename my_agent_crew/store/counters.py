"""Counts of what happens often and leaves no row of its own: a prompt sent with old tool
output trimmed out, a tool output kept on disk, a kit hook run, a command invoked. One row
per day, kind, agent and name, added to as it happens, so the count outlives a restart
and a usage report can say what is used and what never is. Names only: a tool, a hook's
command line, a command; never an argument or a message.

The table is made here rather than in `schema.py`: nothing else reads it, and a store
opened by an older version simply gains it."""

from __future__ import annotations

import logging
import sqlite3
import threading
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

PROMPT_TRIM, SPILL, COMMAND = "prompt_trim", "spill", "command"
HOOK_RUN, HOOK_BLOCK = "hook", "hook_block"
NAME_CHARS = 120
_TABLE = """
CREATE TABLE IF NOT EXISTS usage_counters (
    day TEXT NOT NULL, kind TEXT NOT NULL, agent_id TEXT NOT NULL, name TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (day, kind, agent_id, name)
)
"""


def utc_day(moment: datetime | None = None) -> str:
    return (moment or datetime.now(UTC)).astimezone(UTC).date().isoformat()


class CounterStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock
        with self._lock:
            self._conn.execute(_TABLE)
            self._conn.commit()

    def add(self, kind: str, agent_id: str, name: str = "", day: str | None = None) -> None:
        """One more of `kind` for the agent today. A count that cannot be written is
        logged and dropped: counting must never be what stops a turn."""
        try:
            with self._lock:
                self._conn.execute(
                    "INSERT INTO usage_counters (day, kind, agent_id, name, count)"
                    " VALUES (?,?,?,?,1) ON CONFLICT(day, kind, agent_id, name)"
                    " DO UPDATE SET count = count + 1",
                    (day or utc_day(), kind, agent_id, name[:NAME_CHARS]),
                )
                self._conn.commit()
        except sqlite3.Error:
            logger.exception("could not count %s for agent %s", kind, agent_id)

    def since(self, day: str) -> list[dict[str, Any]]:
        """Totals per kind, agent and name over the UTC days from `day` on."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT kind, agent_id, name, SUM(count) AS count FROM usage_counters"
                " WHERE day >= ? GROUP BY kind, agent_id, name ORDER BY kind, agent_id, name",
                (day,),
            ).fetchall()
        return [dict(row) for row in rows]
