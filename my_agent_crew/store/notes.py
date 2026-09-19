"""Long-term notes the agent saves and searches across conversations."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime


class NoteStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def add(self, text: str) -> int:
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO notes (text, created_at) VALUES (?, ?)", (text.strip(), stamp)
            )
            self._conn.commit()
        return int(cur.lastrowid or 0)

    def count(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0])

    def search(self, query: str, limit: int = 10) -> list[tuple[int, str, str]]:
        """Case-insensitive substring match on every whitespace-separated term."""
        terms = [t for t in query.lower().split() if t]
        where = " AND ".join("lower(text) LIKE ?" for _ in terms) or "1 = 1"
        params = [f"%{t}%" for t in terms] + [limit]
        with self._lock:
            rows = self._conn.execute(
                f"SELECT id, text, created_at FROM notes WHERE {where}"
                " ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [(r["id"], r["text"], r["created_at"]) for r in rows]
