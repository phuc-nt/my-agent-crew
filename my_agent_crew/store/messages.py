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

# The next seq is read and the row written in the same statement, and the row comes
# straight back: one round trip where there used to be three. Selecting from the
# conversation row makes an unknown conversation insert nothing instead of failing later.
_INSERT = (
    "INSERT INTO messages (conversation_id, seq, role, content, tool_calls, tool_call_id,"
    " name, provider, model, cost_usd, created_at, prompt_tokens, completion_tokens,"
    " reasoning_tokens)"
    " SELECT id, COALESCE((SELECT MAX(seq) FROM messages WHERE conversation_id = ?), 0) + 1,"
    " ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? FROM conversations WHERE id = ? RETURNING *"
)


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
        """Raises KeyError for an unknown conversation, with nothing written."""
        tool_calls = json.dumps([asdict(tc) for tc in message.tool_calls])
        values = [conv_id, message.role, message.content, tool_calls, message.tool_call_id]
        values += [message.name, provider, model, cost_usd, stamp]
        values += [prompt_tokens, completion_tokens, reasoning_tokens, conv_id]
        with self._lock:
            rows = self._conn.execute(_INSERT, values).fetchall()
            if not rows:
                raise KeyError(conv_id)
            self._conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (stamp, conv_id)
            )
            self._conn.commit()
        return StoredMessage.from_row(rows[0])

    def history(self, conv_id: str) -> list[StoredMessage]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY seq", (conv_id,)
            ).fetchall()
        return [StoredMessage.from_row(r) for r in rows]
