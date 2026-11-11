"""The messages a chat was sent with a request's buttons, kept so a restart still knows
which to rewrite once the request is settled (`channels/telegram_told.py` decides when).

A row is one message: whose chat it went to (`owner`, the agent the chat talks to), the
request it asks about, the text it was sent with, when the request was first told, and
whether the reminder of it has been sent."""

from __future__ import annotations

import sqlite3
import threading


class ToldStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def all(self, owner: str) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(
                "SELECT approval_id, message_id, text, told_at, reminded FROM telegram_told"
                " WHERE owner = ? ORDER BY rowid",
                (owner,),
            ).fetchall()

    def put(self, owner: str, approval_id: str, message_id: int, text: str, at: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO telegram_told (owner, approval_id, message_id, text, told_at)"
                " VALUES (?,?,?,?,?) ON CONFLICT(owner, approval_id, message_id)"
                " DO UPDATE SET text = excluded.text",
                (owner, approval_id, message_id, text, at),
            )
            self._conn.commit()

    def reminded(self, owner: str, approval_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE telegram_told SET reminded = 1 WHERE owner = ? AND approval_id = ?",
                (owner, approval_id),
            )
            self._conn.commit()

    def forget(self, owner: str, approval_id: str, message_id: int | None = None) -> None:
        """One message of a request, or all of them."""
        one = "" if message_id is None else " AND message_id = ?"
        params = (owner, approval_id) if message_id is None else (owner, approval_id, message_id)
        with self._lock:
            self._conn.execute(
                f"DELETE FROM telegram_told WHERE owner = ? AND approval_id = ?{one}", params
            )
            self._conn.commit()
