"""Approval rows: one per tool call that a human must confirm before it runs."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime

from my_agent_crew.llm.types import ToolCall
from my_agent_crew.store.models import Approval

PENDING, APPROVED, DENIED = "pending", "approved", "denied"


class ApprovalStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def create(self, conv_id: str, message_id: int, call: ToolCall) -> Approval:
        approval_id = uuid.uuid4().hex[:12]
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        with self._lock:
            self._conn.execute(
                "INSERT INTO approvals (id, conversation_id, message_id, tool_call_id, tool_name,"
                " arguments, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (
                    approval_id,
                    conv_id,
                    message_id,
                    call.id,
                    call.name,
                    json.dumps(call.arguments),
                    PENDING,
                    stamp,
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

    def resolve(self, approval_id: str, approve: bool) -> Approval:
        status = APPROVED if approve else DENIED
        with self._lock:
            cur = self._conn.execute(
                "UPDATE approvals SET status = ? WHERE id = ? AND status = ?",
                (status, approval_id, PENDING),
            )
            self._conn.commit()
        if cur.rowcount == 0:
            raise KeyError(approval_id)
        return self.get(approval_id)
