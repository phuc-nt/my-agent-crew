"""Schedules an agent proposed from chat and a person approved. Kept apart from the
profile's own `schedules:` list so `agent.yaml` never needs a write path, and so deleting
one of these can never touch a line the maintainer wrote by hand.

The count-then-insert that enforces the per-agent cap runs inside one `BEGIN IMMEDIATE`
transaction: two approvals racing at the boundary must not both get through, since the
whole point of the cap is a hard ceiling, not a target."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class ScheduleLimitError(Exception):
    """Raised when an agent already holds as many chat-created schedules as it is allowed."""


@dataclass(frozen=True)
class CreatedScheduleRow:
    id: str
    agent_id: str
    name: str
    cron: str | None
    every: str | None
    prompt: str
    skills: tuple[str, ...]
    created_by_conversation: str
    created_at: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> CreatedScheduleRow:
        return cls(
            id=row["id"],
            agent_id=row["agent_id"],
            name=row["name"],
            cron=row["cron"],
            every=row["every"],
            prompt=row["prompt"],
            skills=tuple(json.loads(row["skills"])),
            created_by_conversation=row["created_by_conversation"],
            created_at=row["created_at"],
        )


def _new_id() -> str:
    return f"chat-{uuid.uuid4().hex[:8]}"


class CreatedSchedulesStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def add(self, fields: dict[str, Any], cap: int) -> CreatedScheduleRow:
        """Inserts one row for `fields["agent_id"]`, refusing once that agent already holds
        `cap` of them. `BEGIN IMMEDIATE` takes the write lock before the count is read, so a
        second thread's `add` blocks until this one commits or rolls back — the count it
        eventually sees already reflects this row, or this row never landed at all."""
        agent_id = str(fields["agent_id"])
        row_id, stamp = _new_id(), datetime.now(UTC).isoformat(timespec="seconds")
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                [(count,)] = self._conn.execute(
                    "SELECT COUNT(*) FROM created_schedules WHERE agent_id = ?", (agent_id,)
                )
                if count >= cap:
                    raise ScheduleLimitError(agent_id)
                [row] = self._conn.execute(
                    "INSERT INTO created_schedules (id, agent_id, name, cron, every, prompt,"
                    " skills, created_by_conversation, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?) RETURNING *",
                    (
                        row_id,
                        agent_id,
                        str(fields["name"]),
                        fields.get("cron"),
                        fields.get("every"),
                        str(fields["prompt"]),
                        json.dumps(list(fields.get("skills") or [])),
                        str(fields["created_by_conversation"]),
                        stamp,
                    ),
                ).fetchall()
            except BaseException:
                self._conn.rollback()
                raise
            else:
                self._conn.commit()
        return CreatedScheduleRow.from_row(row)

    def all(self) -> list[CreatedScheduleRow]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM created_schedules ORDER BY created_at, rowid"
            ).fetchall()
        return [CreatedScheduleRow.from_row(r) for r in rows]

    def remove(self, schedule_id: str, agent_id: str) -> bool:
        """True when a row was actually deleted; the caller decides what a missing row means
        (already gone vs. never existed look the same from here, and both are fine to treat
        as "nothing left to delete")."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM created_schedules WHERE id = ? AND agent_id = ?",
                (schedule_id, agent_id),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def count(self, agent_id: str) -> int:
        with self._lock:
            [(count,)] = self._conn.execute(
                "SELECT COUNT(*) FROM created_schedules WHERE agent_id = ?", (agent_id,)
            )
        return count
