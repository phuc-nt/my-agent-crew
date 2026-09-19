"""SQLite store. One connection guarded by a lock; every write commits immediately."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from my_agent_crew.llm.types import Message
from my_agent_crew.store.approvals import ApprovalStore
from my_agent_crew.store.models import Conversation, StoredMessage
from my_agent_crew.store.notes import NoteStore
from my_agent_crew.texts import CONVERSATION_TITLE_DEFAULT

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    autonomous INTEGER NOT NULL DEFAULT 0, cost_cap_usd REAL NOT NULL, skills TEXT NOT NULL,
    spent_usd REAL NOT NULL DEFAULT 0, unknown_cost_calls INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'idle'
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT NOT NULL, seq INTEGER NOT NULL,
    role TEXT NOT NULL, content TEXT NOT NULL, tool_calls TEXT NOT NULL, tool_call_id TEXT,
    name TEXT, provider TEXT, model TEXT, cost_usd REAL, created_at TEXT NOT NULL,
    UNIQUE (conversation_id, seq)
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, message_id INTEGER NOT NULL,
    tool_call_id TEXT NOT NULL, tool_name TEXT NOT NULL, arguments TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE (conversation_id, tool_call_id)
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, created_at TEXT NOT NULL
);
"""

MUTABLE_FIELDS = {"title", "autonomous", "cost_cap_usd", "skills", "status"}


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
            self._conn.executescript(SCHEMA)
        self.approvals = ApprovalStore(self._conn, self._lock)
        self.notes = NoteStore(self._conn, self._lock)

    def close(self) -> None:
        self._conn.close()

    # --- conversations -------------------------------------------------------------------

    def create(
        self,
        title: str = CONVERSATION_TITLE_DEFAULT,
        autonomous: bool = False,
        cost_cap_usd: float = 0.5,
        skills: tuple[str, ...] = (),
    ) -> Conversation:
        conv_id, stamp = new_id(), now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at, autonomous,"
                " cost_cap_usd, skills) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (conv_id, title, stamp, stamp, int(autonomous), cost_cap_usd, json.dumps(skills)),
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

    def list(self) -> list[Conversation]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM conversations ORDER BY updated_at DESC, rowid DESC"
            ).fetchall()
        return [Conversation.from_row(r) for r in rows]

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
        self.get(conv_id)
        stamp = now_iso()
        with self._lock:
            seq = self._conn.execute(
                "SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE conversation_id = ?",
                (conv_id,),
            ).fetchone()[0]
            cur = self._conn.execute(
                "INSERT INTO messages (conversation_id, seq, role, content, tool_calls,"
                " tool_call_id,"
                " name, provider, model, cost_usd, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    conv_id,
                    seq,
                    message.role,
                    message.content,
                    json.dumps([asdict(tc) for tc in message.tool_calls]),
                    message.tool_call_id,
                    message.name,
                    provider,
                    model,
                    cost_usd,
                    stamp,
                ),
            )
            self._conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (stamp, conv_id),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM messages WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
        return StoredMessage.from_row(row)

    def history(self, conv_id: str) -> list[StoredMessage]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY seq", (conv_id,)
            ).fetchall()
        return [StoredMessage.from_row(r) for r in rows]
