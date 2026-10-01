"""SQLite store. One connection (`connection.py`) guarded by a lock; every write commits
immediately and reads its own row back with RETURNING, so one statement does what used
to take two. Tables live in `schema.py`; approvals and runs have their own small stores."""

from __future__ import annotations

import json
import threading
from pathlib import Path

from my_agent_crew.llm.types import Message
from my_agent_crew.store.approvals import ApprovalStore
from my_agent_crew.store.connection import connect
from my_agent_crew.store.conversation_lookup import ConversationLookups
from my_agent_crew.store.created_schedules import CreatedSchedulesStore
from my_agent_crew.store.fork import Forks
from my_agent_crew.store.job_state import JobStateStore
from my_agent_crew.store.memory_proposals import MemoryProposalStore
from my_agent_crew.store.messages import MessageStore
from my_agent_crew.store.models import Conversation, StoredMessage
from my_agent_crew.store.queue import QueueStore
from my_agent_crew.store.runs import RunStore
from my_agent_crew.store.schema import apply_schema
from my_agent_crew.store.search import SearchStore
from my_agent_crew.store.side_calls import SideCallStore
from my_agent_crew.store.spend import Spending
from my_agent_crew.store.stamps import new_id, now_iso
from my_agent_crew.store.usage import UsageStore
from my_agent_crew.texts import CONVERSATION_TITLE_DEFAULT

MUTABLE_FIELDS = {"title", "autonomous", "cost_cap_usd", "skills", "status", "summary"}
MUTABLE_FIELDS |= {"auto_approve"}
LIST_FIELDS = ("skills", "auto_approve")  # stored as JSON arrays


class Store(ConversationLookups, Forks, Spending):
    def __init__(self, path: Path | str = ":memory:"):
        self._conn = connect(path)
        self._lock = threading.RLock()
        with self._lock:
            apply_schema(self._conn)
        self.approvals = ApprovalStore(self._conn, self._lock)
        self.runs = RunStore(self._conn, self._lock)
        self.messages = MessageStore(self._conn, self._lock)
        self.queue = QueueStore(self._conn, self._lock, self.messages)
        self.proposals = MemoryProposalStore(self._conn, self._lock)
        self.jobs = JobStateStore(self._conn, self._lock)
        self.usage = UsageStore(self._conn, self._lock)
        self.side_calls = SideCallStore(self._conn, self._lock)
        self.search = SearchStore(self._conn, self._lock)
        self.created_schedules = CreatedSchedulesStore(self._conn, self._lock)

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
        approval_ttl_seconds: int | None = None,
        forked_from: str = "",
    ) -> Conversation:
        conv_id, stamp = new_id(), now_iso()
        with self._lock:
            [row] = self._conn.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at, autonomous,"
                " cost_cap_usd, skills, agent_id, channel, parent_call_id, approval_ttl_seconds,"
                " forked_from) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING *",
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
                    approval_ttl_seconds,
                    forked_from,
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

    def update(self, conv_id: str, *, touch: bool = True, **fields: object) -> Conversation:
        """`touch=False` leaves `updated_at` alone, for bookkeeping written in the background
        (a recap, a title): the conversation has not moved, and must not read as new."""
        unknown = set(fields) - MUTABLE_FIELDS
        if unknown:
            raise ValueError(f"not updatable: {sorted(unknown)}")
        for key in LIST_FIELDS:
            if key in fields:
                fields[key] = json.dumps(list(fields[key]))  # type: ignore[arg-type]
        if "autonomous" in fields:
            fields["autonomous"] = int(bool(fields["autonomous"]))
        if touch:
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
            for table in ("messages", "approvals", "queued_messages"):
                self._conn.execute(f"DELETE FROM {table} WHERE conversation_id = ?", (conv_id,))
            # A fork's header links back here; once this conversation is gone that link
            # must go too, or it would point at an id that no longer exists.
            self._conn.execute(
                "UPDATE conversations SET forked_from = '' WHERE forked_from = ?", (conv_id,)
            )
            cur = self._conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            self._conn.commit()
        if cur.rowcount == 0:
            raise KeyError(conv_id)

    # --- messages ------------------------------------------------------------------------

    def append(
        self,
        conv_id: str,
        message: Message,
        provider: str | None = None,
        model: str | None = None,
        cost_usd: float | None = None,
        **tokens: int | None,
    ) -> StoredMessage:
        """`tokens` are the message's prompt_tokens, completion_tokens, reasoning_tokens and
        cached_tokens, each None when the provider did not report it."""
        return self.messages.append(
            conv_id, message, now_iso(), provider, model, cost_usd, **tokens
        )

    def history(self, conv_id: str) -> list[StoredMessage]:
        return self.messages.history(conv_id)
