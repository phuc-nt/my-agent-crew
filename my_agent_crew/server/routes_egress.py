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
def egress(rt: Rt, days: int = Query(DAYS_DEFAULT, ge=1, le=KEEP_DAYS)) -> dict[str, Any]:
    """The window is the last `days` days of the home's zone, today included. What is
    still in memory is written first, so the answer holds the call made a moment ago."""
    COUNTER.flush()
    since = (rt.settings.today() - timedelta(days=days - 1)).isoformat()
    return {
        "days": days,
        "since": since,
        "hosts": rt.store.egress.since(since),
        "not_seen": list(NOT_SEEN),
    }
