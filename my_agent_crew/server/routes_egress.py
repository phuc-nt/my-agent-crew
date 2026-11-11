"""`GET /api/activity/egress`: the hosts this process called over the last days, as calls
per host (`my_agent_crew/egress.py`). Read-only, and host names only."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Query

from my_agent_crew.egress import COUNTER, NOT_SEEN
from my_agent_crew.server.deps import Rt
from my_agent_crew.store.egress import KEEP_DAYS

router = APIRouter(tags=["activity"])
DAYS_DEFAULT = 7


@router.get("/activity/egress")
def egress(
    rt: Rt, days: int = Query(DAYS_DEFAULT, ge=1, le=KEEP_DAYS), by_day: bool = False
) -> dict[str, Any]:
    """The window is the last `days` days of the home's zone, today included. What is
    still in memory is written first, so the answer holds the call made a moment ago.
    `by_day` adds the rows unsummed, for whoever keeps a copy outside this process."""
    COUNTER.flush()
    since = (rt.settings.today() - timedelta(days=days - 1)).isoformat()
    answer: dict[str, Any] = {
        "days": days,
        "since": since,
        "hosts": rt.store.egress.since(since),
        "not_seen": list(NOT_SEEN),
    }
    if by_day:
        answer["rows"] = rt.store.egress.rows_since(since)
    return answer
