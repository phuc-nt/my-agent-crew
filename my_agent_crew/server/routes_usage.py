"""`GET /api/activity/usage`: what the crew used over the last days, as counts by name
(`activity/usage_report.py`). Read-only, and made to decide what can be deleted."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Query

from my_agent_crew.activity.usage_report import usage_report
from my_agent_crew.server.deps import Rt
from my_agent_crew.store.counters import utc_day

router = APIRouter(tags=["activity"])
DAYS_DEFAULT, DAYS_MAX = 30, 366


@router.get("/activity/usage")
def usage(rt: Rt, days: int = Query(DAYS_DEFAULT, ge=1, le=DAYS_MAX)) -> dict[str, Any]:
    """The window is the last `days` days up to now. The day counters are kept per UTC
    day, so theirs opens at the start of the UTC day the window opens in."""
    start = datetime.now(UTC) - timedelta(days=days)
    since = start.isoformat(timespec="seconds")
    report = usage_report(
        rt.store.runs.since(since),
        rt.store.counters.since(utc_day(start)),
        rt.store.usage.by_provider(since),
    )
    return {"days": days, "since": since} | report
