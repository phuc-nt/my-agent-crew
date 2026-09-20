"""Spend and token totals read straight from the message log.

Every assistant message that came from a provider carries its cost and token counts, so
the log is the honest ledger: what was billed is what was written. Runs keep a copy for
the activity rail, but a dashboard adds up messages, not runs."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

BY_DAY_DEFAULT = 7

_TOTALS = (
    "COUNT(*) AS calls, COALESCE(SUM(cost_usd), 0) AS cost_usd,"
    " COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,"
    " COALESCE(SUM(completion_tokens), 0) AS completion_tokens,"
    " SUM(CASE WHEN cost_usd IS NULL THEN 1 ELSE 0 END) AS unknown_cost_calls"
)
_MODEL_CALLS = "role = 'assistant' AND provider IS NOT NULL"


def _totals(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {
            "calls": 0,
            "cost_usd": 0.0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "unknown_cost_calls": 0,
        }
    return {
        "calls": row["calls"],
        "cost_usd": float(row["cost_usd"]),
        "prompt_tokens": int(row["prompt_tokens"]),
        "completion_tokens": int(row["completion_tokens"]),
        "unknown_cost_calls": int(row["unknown_cost_calls"] or 0),
    }


class UsageStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def by_day(
        self, days: int = BY_DAY_DEFAULT, today: datetime | None = None
    ) -> list[dict[str, Any]]:
        """One entry per calendar day (UTC) ending today, oldest first, days with no
        model call included as zeros so a chart keeps its shape."""
        end = (today or datetime.now(UTC)).date()
        first = end - timedelta(days=days - 1)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT substr(created_at, 1, 10) AS day, {_TOTALS} FROM messages"
                f" WHERE {_MODEL_CALLS} AND created_at >= ? GROUP BY day",
                (first.isoformat(),),
            ).fetchall()
        found = {r["day"]: r for r in rows}
        return [
            {"day": (first + timedelta(days=i)).isoformat()}
            | _totals(found.get((first + timedelta(days=i)).isoformat()))
            for i in range(days)
        ]

    def by_model(self) -> list[dict[str, Any]]:
        """Totals per `provider:model` over the whole log, biggest spender first."""
        with self._lock:
            rows = self._conn.execute(
                f"SELECT provider || ':' || model AS model, {_TOTALS} FROM messages"
                f" WHERE {_MODEL_CALLS} GROUP BY model ORDER BY cost_usd DESC, calls DESC"
            ).fetchall()
        return [{"model": r["model"]} | _totals(r) for r in rows]
