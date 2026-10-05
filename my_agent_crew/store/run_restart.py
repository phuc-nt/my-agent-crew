"""What a starting server does with the runs the previous process left open.

A run paused on a request that still waits is held again, so the decision continues it. A
run that was still working was cut by the stop: every such row is closed as interrupted, and
the newest one of each conversation is handed back so the server may take it up again
(`turn_resume.py`). Only a run never taken up before is handed back: one that was cut while
it was already a continuation stays closed, so a turn that brings the server down cannot do
so at every start."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass

from my_agent_crew.store.approvals import PENDING
from my_agent_crew.store.run_record import AWAITING, FAILED, RUNNING, RunRecord

INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class Settled:
    # Still waiting on a person: live again, exactly as they were.
    paused: list[RunRecord]
    # Cut while working, closed, and never continued before.
    cut: list[RunRecord]


def _newest_per_conversation(rows: list[sqlite3.Row], skip: set[str]) -> dict[str, RunRecord]:
    newest: dict[str, RunRecord] = {}
    for row in rows:
        conv_id = row["conversation_id"]
        if conv_id not in newest and conv_id not in skip:
            newest[conv_id] = RunRecord.from_row(row)
    return newest


def settle_after_restart(conn: sqlite3.Connection, lock: threading.RLock, stamp: str) -> Settled:
    """A paused run outlives its process only while its conversation holds a pending
    request: the newest such run per conversation is kept, and every other paused row,
    whose request was settled while nothing held the run, is closed with the cut ones
    instead of waiting forever."""
    newest_first = " ORDER BY started_at DESC, rowid DESC"
    with lock:
        rows = conn.execute(
            "SELECT * FROM runs WHERE status = ? AND conversation_id IN"
            " (SELECT conversation_id FROM approvals WHERE status = ?)" + newest_first,
            (AWAITING, PENDING),
        ).fetchall()
        paused = _newest_per_conversation(rows, set())
        rows = conn.execute(
            "SELECT * FROM runs WHERE status = ? AND resumed = 0"
            " AND conversation_id IS NOT NULL" + newest_first,
            (RUNNING,),
        ).fetchall()
        cut = _newest_per_conversation(rows, set(paused))
        kept = [run.id for run in paused.values()]
        conn.execute(
            "UPDATE runs SET status = ?, finished_at = ?, summary = ?"
            f" WHERE status IN (?, ?) AND id NOT IN ({','.join('?' * len(kept))})",
            (FAILED, stamp, INTERRUPTED, RUNNING, AWAITING, *kept),
        )
        conn.commit()
    for run in cut.values():
        run.status, run.finished_at, run.summary = FAILED, stamp, INTERRUPTED
    return Settled(list(paused.values()), list(cut.values()))
