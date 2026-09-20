"""SQLite store. One connection guarded by a lock; every write commits immediately.
Tables live in `schema.py`; approvals and runs have their own small stores."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from my_agent_crew.llm.types import Message
from my_agent_crew.store.approvals import ApprovalStore
from my_agent_crew.store.channel_state import ChannelStateStore
from my_agent_crew.store.memory_proposals import MemoryProposalStore
from my_agent_crew.store.messages import MessageStore
from my_agent_crew.store.models import Conversation, StoredMessage
from my_agent_crew.store.runs import RunStore
from my_agent_crew.store.schema import apply_schema
from my_agent_crew.texts import CONVERSATION_TITLE_DEFAULT

MUTABLE_FIELDS = {"title", "autonomous", "cost_cap_usd", "skills", "status", "summary"}


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class Store:
    def __init__(self, path: Path | str = ":memory:"):
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            apply_schema(self._conn)
        self.approvals = ApprovalStore(self._conn, self._lock)
        self.runs = RunStore(self._conn, self._lock)
        self.channels = ChannelStateStore(self._conn, self._lock)
        self.messages = MessageStore(self._conn, self._lock)
        self.proposals = MemoryProposalStore(self._conn, self._lock)

    def close(self) -> None:
        self._conn.close()

    # --- conversations -------------------------------------------------------------------

    def create(
        self,
        title: str = CONVERSATION_TITLE_DEFAULT,
        autonomous: bool = False,
        cost_cap_usd: float = 0.5,
        skills: tuple[str, ...] = (),
        agent_id: str = "default",
        channel: str = "",
    ) -> Conversation:
        conv_id, stamp = new_id(), now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at, autonomous,"
                " cost_cap_usd, skills, agent_id, channel) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    conv_id,
                    title,
                    stamp,
                    stamp,
                    int(autonomous),
                    cost_cap_usd,
                    json.dumps(skills),
                    agent_id,
                    channel,
                ),
            )
            self._conn.commit()
        return self.get(conv_id)

    def get(self, conv_id: str) -> Conversation:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM conversations WHERE id = ?", (conv_id,)
            ).fetchone()
        if row is None:
            raise KeyError(conv_id)
        return Conversation.from_row(row)

    def list(self, agent_id: str | None = None) -> list[Conversation]:
        where, params = ("", ()) if agent_id is None else (" WHERE agent_id = ?", (agent_id,))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM conversations{where} ORDER BY updated_at DESC, rowid DESC", params
            ).fetchall()
        return [Conversation.from_row(r) for r in rows]

    def latest_for_channel(self, agent_id: str, channel: str) -> Conversation | None:
        """The newest conversation an agent holds on a channel, by creation time."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM conversations WHERE agent_id = ? AND channel = ?"
                " ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (agent_id, channel),
            ).fetchone()
        return Conversation.from_row(row) if row else None

    def previous_for_channel(self, agent_id: str, channel: str, before: str) -> Conversation | None:
        """The conversation this agent held on the channel right before `before`. Ordered
        by rowid, not `created_at`: two conversations opened in the same millisecond carry
        the same timestamp, and only insertion order tells them apart."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM conversations WHERE agent_id = ? AND channel = ?"
                " AND rowid < (SELECT rowid FROM conversations WHERE id = ?)"
                " ORDER BY rowid DESC LIMIT 1",
                (agent_id, channel, before),
            ).fetchone()
        return Conversation.from_row(row) if row else None

    def set_current_agent(self, channel: str, agent_id: str) -> None:
        self.channels.set_current_agent(channel, agent_id, now_iso())

    def update(self, conv_id: str, **fields: object) -> Conversation:
        unknown = set(fields) - MUTABLE_FIELDS
        if unknown:
            raise ValueError(f"not updatable: {sorted(unknown)}")
        if "skills" in fields:
            fields["skills"] = json.dumps(list(fields["skills"]))  # type: ignore[arg-type]
        if "autonomous" in fields:
            fields["autonomous"] = int(bool(fields["autonomous"]))
        fields["updated_at"] = now_iso()
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE conversations SET {assignments} WHERE id = ?", (*fields.values(), conv_id)
            )
            self._conn.commit()
        if cur.rowcount == 0:
            raise KeyError(conv_id)
        return self.get(conv_id)

    def delete(self, conv_id: str) -> None:
        with self._lock:
            for table in ("messages", "approvals"):
                self._conn.execute(f"DELETE FROM {table} WHERE conversation_id = ?", (conv_id,))
            cur = self._conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            self._conn.commit()
        if cur.rowcount == 0:
            raise KeyError(conv_id)

    def add_spend(self, conv_id: str, cost_usd: float | None) -> Conversation:
        column = (
            "spent_usd = spent_usd + ?"
            if cost_usd is not None
            else "unknown_cost_calls = unknown_cost_calls + ?"
        )
        with self._lock:
            self._conn.execute(
                f"UPDATE conversations SET {column}, updated_at = ? WHERE id = ?",
                (cost_usd if cost_usd is not None else 1, now_iso(), conv_id),
            )
            self._conn.commit()
        return self.get(conv_id)

    # --- messages ------------------------------------------------------------------------

    def append(
        self,
        conv_id: str,
        message: Message,
        provider: str | None = None,
        model: str | None = None,
        cost_usd: float | None = None,
    ) -> StoredMessage:
        self.get(conv_id)  # an unknown conversation must raise before anything is written
        return self.messages.append(conv_id, message, now_iso(), provider, model, cost_usd)

    def history(self, conv_id: str) -> list[StoredMessage]:
        return self.messages.history(conv_id)
