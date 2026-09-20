"""Per-channel state: which agent a chat is currently talking to when one bot serves
several. Kept explicit rather than derived from conversation timestamps, so a scheduled
brief delivered to the chat never switches the agent behind the user's back."""

from __future__ import annotations

import sqlite3
import threading


class ChannelStateStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def current_agent(self, channel: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT agent_id FROM channel_state WHERE channel = ?", (channel,)
            ).fetchone()
        return row["agent_id"] if row else None

    def set_current_agent(self, channel: str, agent_id: str, stamp: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO channel_state (channel, agent_id, updated_at) VALUES (?,?,?)"
                " ON CONFLICT(channel) DO UPDATE SET agent_id = excluded.agent_id,"
                " updated_at = excluded.updated_at",
                (channel, agent_id, stamp),
            )
            self._conn.commit()
