"""Spend and token totals read straight from the message log.

Every assistant message that came from a provider carries its cost and token counts, so
the log is the honest ledger: what was billed is what was written. Runs keep a copy for
the activity rail, but a dashboard adds up messages, not runs."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any

from my_agent_crew.clock import day_start_utc, local_day

BY_DAY_DEFAULT = 7

_TOTALS = (
    "COUNT(*) AS calls, COALESCE(SUM(cost_usd), 0) AS cost_usd,"
    " COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,"
    " COALESCE(SUM(completion_tokens), 0) AS completion_tokens,"
    " COALESCE(SUM(cached_tokens), 0) AS cached_tokens,"
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
            "cached_tokens": 0,
            "unknown_cost_calls": 0,
        }
    return {
        "calls": row["calls"],
        "cost_usd": float(row["cost_usd"]),
        "prompt_tokens": int(row["prompt_tokens"]),
        "completion_tokens": int(row["completion_tokens"]),
        "cached_tokens": int(row["cached_tokens"]),
        "unknown_cost_calls": int(row["unknown_cost_calls"] or 0),
    }


class UsageStore:
    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock):
        self._conn = conn
        self._lock = lock

    def by_day(
        self,
        days: int = BY_DAY_DEFAULT,
        today: datetime | None = None,
        zone: tzinfo = UTC,
    ) -> list[dict[str, Any]]:
        """One entry per calendar day in `zone` ending today, oldest first, days with no
        model call included as zeros so a chart keeps its shape. Stamps are UTC, so the
        day a call belongs to is worked out here rather than by cutting the stamp."""
        end = (today or datetime.now(UTC)).astimezone(zone).date()
        first = end - timedelta(days=days - 1)
        with self._lock:
            rows = self._conn.execute(
                "SELECT created_at, cost_usd, prompt_tokens, completion_tokens, cached_tokens"
                " FROM messages"
                f" WHERE {_MODEL_CALLS} AND created_at >= ?",
                (day_start_utc(first, zone),),
            ).fetchall()
        buckets = {(first + timedelta(days=i)).isoformat(): _totals(None) for i in range(days)}
        for row in rows:
            bucket = buckets.get(local_day(row["created_at"], zone))
            if bucket is None:
                continue
            bucket["calls"] += 1
            bucket["cost_usd"] += row["cost_usd"] or 0.0
            bucket["prompt_tokens"] += row["prompt_tokens"] or 0
            bucket["completion_tokens"] += row["completion_tokens"] or 0
            bucket["cached_tokens"] += row["cached_tokens"] or 0
            bucket["unknown_cost_calls"] += row["cost_usd"] is None
        return [{"day": day} | totals for day, totals in buckets.items()]

    def by_model(self) -> list[dict[str, Any]]:
        """Totals per `provider:model` over the whole log, biggest spender first."""
        with self._lock:
            rows = self._conn.execute(
                f"SELECT provider || ':' || model AS model, {_TOTALS} FROM messages"
                f" WHERE {_MODEL_CALLS} GROUP BY model ORDER BY cost_usd DESC, calls DESC"
            ).fetchall()
        return [{"model": r["model"]} | _totals(r) for r in rows]
