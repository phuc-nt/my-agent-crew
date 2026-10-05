"""A run as it is stored and sent: one turn or scheduled job, its status and its steps."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any

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
    # Taken up again after a restart cut it. A run is continued once, so one that is cut
    # a second time is closed instead of starting the server on the same work for ever.
    resumed: bool = False

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
            "resumed": self.resumed,
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
            resumed=bool(row["resumed"]),
        )
