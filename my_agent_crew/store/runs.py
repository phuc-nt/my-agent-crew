"""Runs: one row per turn or scheduled job, with its step timeline. This is what the
activity view reads, and it outlives the process so yesterday's job is still visible."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from my_agent_crew.store.approvals import PENDING

RUNNING = "running"
AWAITING = "awaiting_approval"
DONE = "done"
HALTED = "halted"
FAILED = "error"
ACTIVE_STATUSES = (RUNNING, AWAITING)


@dataclass
class RunRecord:
    id: str
    agent_id: str
    conversation_id: str | None
    source: str
    title: str
    status: str
    started_at: str
    finished_at: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)
    spent_usd: float = 0.0
    unknown_cost_calls: int = 0
    summary: str = ""
    after_seq: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "conversation_id": self.conversation_id,
            "source": self.source,
            "title": self.title,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            # Copies, not the live list: a payload waits in a watcher's queue and is
            # serialised later, by which time the run has moved on. Keys starting with
            # "_" are the step builder's own bookkeeping and never leave the process.
            "steps": [
                {key: value for key, value in step.items() if not key.startswith("_")}
                for step in self.steps
            ],
            "spent_usd": self.spent_usd,
            "unknown_cost_calls": self.unknown_cost_calls,
            "summary": self.summary,
        }

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> RunRecord:
        return cls(
            id=row["id"],
            agent_id=row["agent_id"],
            conversation_id=row["conversation_id"],
            source=row["source"],
            title=row["title"],
            status=row["status"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            steps=json.loads(row["steps"]),
            spent_usd=row["spent_usd"],
            unknown_cost_calls=row["unknown_cost_calls"],
            summary=row["summary"],
            after_seq=row["after_seq"],
        )


class RunStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def save(self, run: RunRecord) -> None:
        """An upsert rather than a replace, so a run keeps the rowid it was created with:
        runs that began in the same second are told apart by it."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO runs (id, agent_id, conversation_id, source, title, status,"
                " started_at, finished_at, steps, spent_usd, unknown_cost_calls, summary,"
                " after_seq) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET"
                " agent_id = excluded.agent_id, conversation_id = excluded.conversation_id,"
                " source = excluded.source, title = excluded.title, status = excluded.status,"
                " started_at = excluded.started_at, finished_at = excluded.finished_at,"
                " steps = excluded.steps, spent_usd = excluded.spent_usd,"
                " unknown_cost_calls = excluded.unknown_cost_calls, summary = excluded.summary,"
                " after_seq = excluded.after_seq",
                (
                    run.id,
                    run.agent_id,
                    run.conversation_id,
                    run.source,
                    run.title,
                    run.status,
                    run.started_at,
                    run.finished_at,
                    json.dumps(run.steps, ensure_ascii=False),
                    run.spent_usd,
                    run.unknown_cost_calls,
                    run.summary,
                    run.after_seq,
                ),
            )
            self._conn.commit()

    def get(self, run_id: str) -> RunRecord:
        with self._lock:
            row = self._conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return RunRecord.from_row(row)

    def recent(
        self,
        limit: int = 50,
        source_prefix: str | None = None,
        conversation_ids: Sequence[str] | None = None,
        source: str | None = None,
        agent_id: str | None = None,
    ) -> list[RunRecord]:
        """Newest runs first, optionally only one source, one agent or some conversations.

        Narrowing belongs here rather than in the caller: filtering an already-truncated
        crew-wide page would hide a quiet conversation's runs behind a busy crew's."""
        clauses: list[str] = []
        params: tuple[Any, ...] = ()
        if source_prefix:
            clauses.append("source LIKE ?")
            params += (f"{source_prefix}%",)
        if source is not None:
            clauses.append("source = ?")
            params += (source,)
        if agent_id is not None:
            clauses.append("agent_id = ?")
            params += (agent_id,)
        if conversation_ids is not None:
            ids = tuple(conversation_ids)
            if not ids:
                return []
            clauses.append(f"conversation_id IN ({','.join('?' * len(ids))})")
            params += ids
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM runs{where} ORDER BY started_at DESC, rowid DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
        return [RunRecord.from_row(r) for r in rows]

    def latest_for_conversation(self, conv_id: str) -> RunRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM runs WHERE conversation_id = ?"
                " ORDER BY started_at DESC, rowid DESC LIMIT 1",
                (conv_id,),
            ).fetchone()
        return RunRecord.from_row(row) if row else None

    def settle_after_restart(self, stamp: str) -> list[RunRecord]:
        """Closes the runs the previous process left open, and returns the paused ones a
        decision can still continue.

        A run still 'running' died with that process. A paused run outlives it only while
        its conversation holds a pending request: the newest such run per conversation is
        handed back for the hub to hold, and every other paused row, whose request was
        settled while nothing held the run, is closed too instead of waiting forever."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM runs WHERE status = ? AND conversation_id IN"
                " (SELECT conversation_id FROM approvals WHERE status = ?)"
                " ORDER BY started_at DESC, rowid DESC",
                (AWAITING, PENDING),
            ).fetchall()
            paused: dict[str, RunRecord] = {}
            for row in rows:
                if row["conversation_id"] not in paused:
                    paused[row["conversation_id"]] = RunRecord.from_row(row)
            kept = [run.id for run in paused.values()]
            self._conn.execute(
                "UPDATE runs SET status = ?, finished_at = ?, summary = 'interrupted'"
                f" WHERE status IN (?, ?) AND id NOT IN ({','.join('?' * len(kept))})",
                (FAILED, stamp, RUNNING, AWAITING, *kept),
            )
            self._conn.commit()
        return list(paused.values())
