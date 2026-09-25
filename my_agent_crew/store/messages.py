"""The message log of a conversation. Every turn's state is reconstructed from this log,
so messages are append-only and ordered by a per-conversation sequence number rather than
by timestamp: two messages written in the same millisecond must still keep their order."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict

from my_agent_crew.llm.types import Message
from my_agent_crew.store.models import StoredMessage


class MessageStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def append(
        self,
        conv_id: str,
        message: Message,
        stamp: str,
        provider: str | None = None,
        model: str | None = None,
        cost_usd: float | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        reasoning_tokens: int | None = None,
    ) -> StoredMessage:
        tool_calls = json.dumps([asdict(tc) for tc in message.tool_calls])
        with self._lock:
            seq = self._conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE conversation_id = ?",
                (conv_id,),
            ).fetchone()[0]
            values = [conv_id, seq, message.role, message.content, tool_calls]
            values += [message.tool_call_id, message.name, provider, model, cost_usd, stamp]
            values += [prompt_tokens, completion_tokens, reasoning_tokens]
            cur = self._conn.execute(
                "INSERT INTO messages (conversation_id, seq, role, content, tool_calls,"
                " tool_call_id, name, provider, model, cost_usd, created_at,"
                " prompt_tokens, completion_tokens, reasoning_tokens)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                values,
            )
            self._conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (stamp, conv_id)
            )
            self._conn.commit()
            row = self._conn.execute("SELECT * FROM messages WHERE id = ?", (cur.lastrowid,))
        return StoredMessage.from_row(row.fetchone())

    def history(self, conv_id: str) -> list[StoredMessage]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY seq", (conv_id,)
            ).fetchall()
        return [StoredMessage.from_row(r) for r in rows]
