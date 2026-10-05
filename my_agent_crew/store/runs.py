"""Runs: one row per turn or scheduled job, with its step timeline. This is what the
activity view reads, and it outlives the process so yesterday's job is still visible."""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Sequence
from typing import Any

from my_agent_crew.store.run_record import (
    ACTIVE_STATUSES,
    AWAITING,
    DONE,
    FAILED,
    HALTED,
    RUNNING,
    RunRecord,
)
from my_agent_crew.store.run_restart import Settled, settle_after_restart

__all__ = ["ACTIVE_STATUSES", "AWAITING", "DONE", "FAILED", "HALTED", "RUNNING"]
__all__ += ["RunRecord", "RunStore", "Settled"]


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
                " after_seq, resumed) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET"
                " agent_id = excluded.agent_id, conversation_id = excluded.conversation_id,"
                " source = excluded.source, title = excluded.title, status = excluded.status,"
                " started_at = excluded.started_at, finished_at = excluded.finished_at,"
                " steps = excluded.steps, spent_usd = excluded.spent_usd,"
                " unknown_cost_calls = excluded.unknown_cost_calls, summary = excluded.summary,"
                " after_seq = excluded.after_seq, resumed = excluded.resumed",
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
                    int(run.resumed),
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

    def settle_after_restart(self, stamp: str) -> Settled:
        """Closes the runs the previous process left open (`run_restart.py`)."""
        return settle_after_restart(self._conn, self._lock, stamp)
