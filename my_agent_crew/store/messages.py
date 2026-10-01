"""The message log of a conversation. Every turn's state is reconstructed from this log,
so messages are append-only and ordered by a per-conversation sequence number rather than
by timestamp: two messages written in the same millisecond must still keep their order."""

from __future__ import annotations

import json
import sqlite3
import threading

from my_agent_crew.llm.types import Message
from my_agent_crew.store.message_models import StoredMessage

# The next seq is read and the row written in the same statement, and the row comes
# straight back: one round trip where there used to be three. Selecting from the
# conversation row makes an unknown conversation insert nothing instead of failing later.
_INSERT = (
    "INSERT INTO messages (conversation_id, seq, role, content, tool_calls, tool_call_id,"
    " name, provider, model, cost_usd, created_at, prompt_tokens, completion_tokens,"
    " reasoning_tokens, cached_tokens)"
    " SELECT id, COALESCE((SELECT MAX(seq) FROM messages WHERE conversation_id = ?), 0) + 1,"
    " ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ? FROM conversations WHERE id = ? RETURNING *"
)


# A run's own messages: those after where its conversation stood when the run began, up to
# where the next run in that conversation began. Stamps have one-second resolution, so two
# runs that began in the same second are ordered by that seq instead, and by the order they
# were created in when the first wrote nothing and both began at the same seq.
_OF_RUN = (
    "SELECT * FROM messages WHERE conversation_id = :conv AND seq > :after AND seq <= COALESCE("
    "(SELECT MIN(after_seq) FROM runs WHERE conversation_id = :conv AND id != :run"
    " AND (started_at > :started OR (started_at = :started AND (after_seq > :after"
    " OR (after_seq = :after AND rowid > (SELECT rowid FROM runs WHERE id = :run)))))),"
    " 9223372036854775807) ORDER BY seq"
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
        cached_tokens: int | None = None,
    ) -> StoredMessage:
        """Raises KeyError for an unknown conversation, with nothing written."""
        tool_calls = json.dumps([tc.to_dict() for tc in message.tool_calls])
        values = [conv_id, message.role, message.content, tool_calls, message.tool_call_id]
        values += [message.name, provider, model, cost_usd, stamp]
        values += [prompt_tokens, completion_tokens, reasoning_tokens, cached_tokens, conv_id]
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

    def max_seq(self, conv_id: str) -> int:
        """The seq of the conversation's last message, 0 when it has none."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM messages WHERE conversation_id = ?", (conv_id,)
            ).fetchone()
        return int(row[0])

    def of_run(
        self, conv_id: str, run_id: str, after_seq: int, started_at: str
    ) -> list[StoredMessage]:
        params = {"conv": conv_id, "run": run_id, "after": after_seq, "started": started_at}
        with self._lock:
            rows = self._conn.execute(_OF_RUN, params).fetchall()
        return [StoredMessage.from_row(r) for r in rows]

    def tool_results(self, conv_id: str, tool_call_id: str, limit: int = 2) -> list[StoredMessage]:
        """The tool messages a call id produced in this conversation, oldest first. More
        than one row means the id was reused for two different calls (see openai_compat's
        uuid fix): the caller decides what to do with that, this just reports what exists."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? AND role = 'tool'"
                " AND tool_call_id = ? ORDER BY seq LIMIT ?",
                (conv_id, tool_call_id, limit),
            ).fetchall()
        return [StoredMessage.from_row(r) for r in rows]

    def stamped_between(self, conv_id: str, start: str, end: str | None) -> list[StoredMessage]:
        """Messages written from `start` to `end`, both included; no `end` means up to now."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? AND created_at >= ?"
                " AND (? IS NULL OR created_at <= ?) ORDER BY seq",
                (conv_id, start, end, end),
            ).fetchall()
        return [StoredMessage.from_row(r) for r in rows]
