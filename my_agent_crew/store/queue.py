"""Messages waiting for a busy conversation.

A message that arrives while its conversation's turn is running waits here, in order. A
follow-up is handed over once the turn ends; a steer, meant for the running turn itself, is
taken by the loop at its next step. Handing over is one transaction: the rows leave this
table in the same commit that writes them to the message log as one user message, so a crash
between the two can neither lose a message nor deliver it twice."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from my_agent_crew import texts
from my_agent_crew.llm.types import Message
from my_agent_crew.store.messages import MessageStore

FOLLOW_UP = "follow_up"
STEER = "steer"
# How many messages one conversation may hold waiting. Past it the sender is told to wait,
# so a sender that keeps posting cannot grow the table without end.
QUEUE_LIMIT = 20


class QueueFull(Exception):
    """The conversation already holds QUEUE_LIMIT waiting messages; str() says so."""


@dataclass(frozen=True)
class QueuedItem:
    id: int
    conversation_id: str
    kind: str
    text: str
    source: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> QueuedItem:
        return cls(
            id=row["id"],
            conversation_id=row["conversation_id"],
            kind=row["kind"],
            text=row["text"],
            source=row["source"],
            created_at=row["created_at"],
        )

    def to_dict(self) -> dict[str, object]:
        return {"id": self.id, "kind": self.kind, "text": self.text}


def _stamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _sorted(rows: list[sqlite3.Row]) -> list[QueuedItem]:
    """RETURNING hands rows back in no promised order; the queue's order is the id's."""
    return sorted((QueuedItem.from_row(r) for r in rows), key=lambda item: item.id)


class QueueStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock, messages: MessageStore):
        self._conn = conn
        self._lock = lock
        self._messages = messages

    def add(self, conv_id: str, kind: str, text: str, source: str) -> tuple[QueuedItem, int]:
        """Queues one message and returns it with its place in line, 1 for the first."""
        with self._lock:
            waiting = self.count(conv_id)
            if waiting >= QUEUE_LIMIT:
                raise QueueFull(texts.QUEUE_FULL.format(limit=QUEUE_LIMIT))
            [row] = self._conn.execute(
                "INSERT INTO queued_messages (conversation_id, kind, text, source, created_at)"
                " VALUES (?, ?, ?, ?, ?) RETURNING *",
                (conv_id, kind, text, source, _stamp()),
            ).fetchall()
            self._conn.commit()
        return QueuedItem.from_row(row), waiting + 1

    def peek_all(self, conv_id: str) -> list[QueuedItem]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM queued_messages WHERE conversation_id = ? ORDER BY id", (conv_id,)
            ).fetchall()
        return [QueuedItem.from_row(r) for r in rows]

    def count(self, conv_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM queued_messages WHERE conversation_id = ?", (conv_id,)
            ).fetchone()
        return row[0]

    def conversations_with_items(self) -> list[str]:
        """Every conversation holding waiting messages, the longest-waiting first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT conversation_id FROM queued_messages"
                " GROUP BY conversation_id ORDER BY MIN(id)"
            ).fetchall()
        return [row[0] for row in rows]

    def deliver(self, conv_id: str, ids: Sequence[int]) -> list[QueuedItem]:
        """Moves these waiting messages into the conversation's log as one user message.
        Returns what moved: fewer than asked when a row was already taken, none when all were.
        """
        if not ids:
            return []
        marks = ", ".join("?" * len(ids))
        with self._lock:
            try:
                items = _sorted(
                    self._conn.execute(
                        "DELETE FROM queued_messages WHERE conversation_id = ?"
                        f" AND id IN ({marks}) RETURNING *",
                        (conv_id, *ids),
                    ).fetchall()
                )
                if items:
                    text = "\n\n".join(item.text for item in items)
                    # Its commit carries the DELETE above: both land, or neither does. The
                    # batch hears the open canvas only when its first message came from the
                    # web chat.
                    message = Message(role="user", content=text)
                    self._messages.append(conv_id, message, _stamp(), note_source=items[0].source)
                else:
                    self._conn.commit()
            except BaseException:
                self._conn.rollback()
                raise
        return items

    def take_steers(self, conv_id: str) -> list[QueuedItem]:
        """Delivers the conversation's waiting steers, leaving its follow-ups in line."""
        with self._lock:
            steers = [item.id for item in self.peek_all(conv_id) if item.kind == STEER]
            return self.deliver(conv_id, steers)

    def take_all(self, conv_id: str) -> list[QueuedItem]:
        """Removes every waiting message without delivering it: the sender withdrew them, or
        their conversation is gone."""
        with self._lock:
            rows = self._conn.execute(
                "DELETE FROM queued_messages WHERE conversation_id = ? RETURNING *", (conv_id,)
            ).fetchall()
            self._conn.commit()
        return _sorted(rows)
