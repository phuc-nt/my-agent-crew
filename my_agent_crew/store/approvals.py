"""Approval rows: one per tool call that a human must confirm before it runs.

An approval carries a deadline. One nobody answers in time is closed as `expired`,
which the loop treats exactly like a denial: the tool never runs, the turn goes on.
Waiting forever would leave a night job hanging until someone notices in the morning."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta

from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store.models import Approval

PENDING, APPROVED, DENIED, EXPIRED = "pending", "approved", "denied", "expired"
DEFAULT_TTL_SECONDS = 600


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds")


class ApprovalStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def create(
        self, conv_id: str, message_id: int, call: ToolCall, ttl_seconds: int = DEFAULT_TTL_SECONDS
    ) -> Approval:
        approval_id = uuid.uuid4().hex[:12]
        now = datetime.now(UTC)
        with self._lock:
            self._conn.execute(
                "INSERT INTO approvals (id, conversation_id, message_id, tool_call_id, tool_name,"
                " arguments, status, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    approval_id,
                    conv_id,
                    message_id,
                    call.id,
                    call.name,
                    json.dumps(call.arguments),
                    PENDING,
                    _stamp(now),
                    _stamp(now + timedelta(seconds=ttl_seconds)),
                ),
            )
            self._conn.commit()
        return self.get(approval_id)

    def get(self, approval_id: str) -> Approval:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM approvals WHERE id = ?", (approval_id,)
            ).fetchone()
        if row is None:
            raise KeyError(approval_id)
        return Approval.from_row(row)

    def find_for_call(self, conv_id: str, tool_call_id: str) -> Approval | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM approvals WHERE conversation_id = ? AND tool_call_id = ?",
                (conv_id, tool_call_id),
            ).fetchone()
        return Approval.from_row(row) if row else None

    def pending(self, conv_id: str) -> Approval | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM approvals WHERE conversation_id = ? AND status = ?"
                " ORDER BY created_at LIMIT 1",
                (conv_id, PENDING),
            ).fetchone()
        return Approval.from_row(row) if row else None

    def overdue(self, now: datetime | None = None) -> list[Approval]:
        """Pending approvals whose deadline has passed, oldest first. Rows written before
        deadlines existed have none and never come back here."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM approvals WHERE status = ? AND expires_at IS NOT NULL"
                " AND expires_at <= ? ORDER BY expires_at",
                (PENDING, _stamp(now or datetime.now(UTC))),
            ).fetchall()
        return [Approval.from_row(r) for r in rows]

    def resolve(self, approval_id: str, approve: bool, status: str | None = None) -> Approval:
        """Close a pending approval. `status` overrides the approve/deny pair for expiry."""
        status = status or (APPROVED if approve else DENIED)
        with self._lock:
            cur = self._conn.execute(
                "UPDATE approvals SET status = ?, resolved_at = ? WHERE id = ? AND status = ?",
                (status, _stamp(datetime.now(UTC)), approval_id, PENDING),
            )
            self._conn.commit()
        if cur.rowcount == 0:
            raise KeyError(approval_id)
        return self.get(approval_id)

    def recent(self, limit: int = 50) -> list[Approval]:
        """Decided approvals, newest decision first — the history a user reviews."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM approvals WHERE status != ?"
                " ORDER BY resolved_at DESC, created_at DESC, rowid DESC LIMIT ?",
                (PENDING, limit),
            ).fetchall()
        return [Approval.from_row(r) for r in rows]
