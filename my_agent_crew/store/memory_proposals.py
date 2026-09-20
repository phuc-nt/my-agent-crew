"""Memory writes that a scheduled job asked for but may not perform on its own.

A job runs unattended, so a fact it wants to remember about the person is held here as a
proposal until someone approves it. Turns the person is present for (chat, Telegram)
write directly and never reach this table.

Applying an approved proposal touches files, which this module does not: see
`memory/proposals_apply.py`.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

USER_FACT, USER_FORGET, AGENT_MEMORY = "user_fact", "user_forget", "agent_memory"
PENDING, APPROVED, REJECTED = "pending", "approved", "rejected"


@dataclass(frozen=True)
class MemoryProposal:
    id: str
    agent_id: str
    kind: str
    name: str
    description: str
    type: str
    body: str
    status: str
    source: str
    created_at: str
    resolved_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> MemoryProposal:
        return cls(
            id=row["id"],
            agent_id=row["agent_id"],
            kind=row["kind"],
            name=row["name"],
            description=row["description"],
            type=row["type"],
            body=row["body"],
            status=row["status"],
            source=row["source"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
        )


class MemoryProposalStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def create(
        self,
        agent_id: str,
        kind: str,
        name: str = "",
        description: str = "",
        type: str = "reference",
        body: str = "",
        source: str = "job",
    ) -> MemoryProposal:
        proposal_id = uuid.uuid4().hex[:12]
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        with self._lock:
            self._conn.execute(
                "INSERT INTO memory_proposals (id, agent_id, kind, name, description, type, body,"
                " status, source, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    proposal_id,
                    agent_id,
                    kind,
                    name,
                    description,
                    type,
                    body,
                    PENDING,
                    source,
                    stamp,
                ),
            )
            self._conn.commit()
        return self.get(proposal_id)

    def get(self, proposal_id: str) -> MemoryProposal:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM memory_proposals WHERE id = ?", (proposal_id,)
            ).fetchone()
        if row is None:
            raise KeyError(proposal_id)
        return MemoryProposal.from_row(row)

    def list(self, status: str | None = PENDING) -> list[MemoryProposal]:
        """Newest first. `status=None` lists every proposal, resolved ones included."""
        query = "SELECT * FROM memory_proposals"
        params: tuple[str, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            params = (status,)
        with self._lock:
            rows = self._conn.execute(query + " ORDER BY created_at DESC, rowid DESC", params)
            return [MemoryProposal.from_row(row) for row in rows.fetchall()]

    def resolve(self, proposal_id: str, approve: bool) -> MemoryProposal:
        """Decide a pending proposal. Deciding one twice raises, so a double click cannot
        apply the same write again."""
        status = APPROVED if approve else REJECTED
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        with self._lock:
            cur = self._conn.execute(
                "UPDATE memory_proposals SET status = ?, resolved_at = ?"
                " WHERE id = ? AND status = ?",
                (status, stamp, proposal_id, PENDING),
            )
            self._conn.commit()
        if cur.rowcount == 0:
            raise KeyError(proposal_id)
        return self.get(proposal_id)
