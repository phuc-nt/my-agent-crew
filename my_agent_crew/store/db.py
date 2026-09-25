"""SQLite store. One connection (`connection.py`) guarded by a lock; every write commits
immediately and reads its own row back with RETURNING, so one statement does what used
to take two. Tables live in `schema.py`; approvals and runs have their own small stores."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from my_agent_crew.llm.types import Message
from my_agent_crew.store import conversation_lookup as lookup
from my_agent_crew.store.approvals import ApprovalStore
from my_agent_crew.store.connection import connect
from my_agent_crew.store.job_state import JobStateStore
from my_agent_crew.store.memory_proposals import MemoryProposalStore
from my_agent_crew.store.messages import MessageStore
from my_agent_crew.store.models import Conversation, StoredMessage
from my_agent_crew.store.runs import RunStore
from my_agent_crew.store.schema import apply_schema
from my_agent_crew.store.usage import UsageStore
from my_agent_crew.texts import CONVERSATION_TITLE_DEFAULT

MUTABLE_FIELDS = {"title", "autonomous", "cost_cap_usd", "skills", "status", "summary"}
MUTABLE_FIELDS |= {"auto_approve"}
LIST_FIELDS = ("skills", "auto_approve")  # stored as JSON arrays


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class Store:
    def __init__(self, path: Path | str = ":memory:"):
        self._conn = connect(path)
        self._lock = threading.RLock()
        with self._lock:
            apply_schema(self._conn)
        self.approvals = ApprovalStore(self._conn, self._lock)
        self.runs = RunStore(self._conn, self._lock)
        self.messages = MessageStore(self._conn, self._lock)
        self.proposals = MemoryProposalStore(self._conn, self._lock)
        self.jobs = JobStateStore(self._conn, self._lock)
        self.usage = UsageStore(self._conn, self._lock)

    def close(self) -> None:
        self._conn.close()

    @property
    def changes(self) -> int:
        """Rows written so far: a version number for anything derived from the store."""
        return self._conn.total_changes

    # --- conversations -------------------------------------------------------------------

    def create(
        self,
        title: str = CONVERSATION_TITLE_DEFAULT,
        autonomous: bool = False,
        cost_cap_usd: float = 0.5,
        skills: tuple[str, ...] = (),
        agent_id: str = "default",
        channel: str = "",
        parent_call_id: str = "",
    ) -> Conversation:
        conv_id, stamp = new_id(), now_iso()
        with self._lock:
            [row] = self._conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at, autonomous,"
                " cost_cap_usd, skills, agent_id, channel, parent_call_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING *",
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
                    parent_call_id,
                ),
            ).fetchall()
            self._conn.commit()
        return Conversation.from_row(row)

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
        return lookup.latest_for_channel(self._conn, self._lock, agent_id, channel)

    def previous_for_channel(self, agent_id: str, channel: str, before: str) -> Conversation | None:
        return lookup.previous_for_channel(self._conn, self._lock, agent_id, channel, before)

    def for_parent_call(self, parent_call_id: str) -> Conversation | None:
        return lookup.for_parent_call(self._conn, self._lock, parent_call_id)

    def children_of(self, call_ids: tuple[str, ...]) -> list[Conversation]:
        return lookup.children_of(self._conn, self._lock, call_ids)

    def delegated_children(self, conv_id: str, tool_name: str) -> list[Conversation]:
        """What this conversation delegated, oldest first, found through its own tool calls."""
        calls = lookup.delegating_call_ids(self.history(conv_id), tool_name)
        return self.children_of(calls)

    def update(self, conv_id: str, **fields: object) -> Conversation:
        unknown = set(fields) - MUTABLE_FIELDS
        if unknown:
            raise ValueError(f"not updatable: {sorted(unknown)}")
        for key in LIST_FIELDS:
            if key in fields:
                fields[key] = json.dumps(list(fields[key]))  # type: ignore[arg-type]
        if "autonomous" in fields:
            fields["autonomous"] = int(bool(fields["autonomous"]))
        fields["updated_at"] = now_iso()
        assignments = ", ".join(f"{k} = ?" for k in fields)
        return self._update_returning(
            f"UPDATE conversations SET {assignments} WHERE id = ? RETURNING *",
            (*fields.values(), conv_id),
        )

    def _update_returning(self, sql: str, params: tuple) -> Conversation:
        """One UPDATE of one conversation, handing back the row it left behind."""
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
            self._conn.commit()
        if not rows:
            raise KeyError(params[-1])
        return Conversation.from_row(rows[0])

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
        return self._update_returning(
            f"UPDATE conversations SET {column}, updated_at = ? WHERE id = ? RETURNING *",
            (cost_usd if cost_usd is not None else 1, now_iso(), conv_id),
        )

    # --- messages ------------------------------------------------------------------------

    def append(
        self,
        conv_id: str,
        message: Message,
        provider: str | None = None,
        model: str | None = None,
        cost_usd: float | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        reasoning_tokens: int | None = None,
    ) -> StoredMessage:
        return self.messages.append(
            conv_id,
            message,
            now_iso(),
            provider,
            model,
            cost_usd,
            prompt_tokens,
            completion_tokens,
            reasoning_tokens,
        )

    def history(self, conv_id: str) -> list[StoredMessage]:
        return self.messages.history(conv_id)
