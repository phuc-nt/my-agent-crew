"""The one job dict the jobs API and the UI both read: `Scheduler.describe()` builds one
of these per job, and keeping the shape in its own function is what stops the API route
and a future caller from quietly drifting into two different ideas of what a job dict has
in it."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from my_agent_crew.scheduler.cron import next_run
from my_agent_crew.scheduler.failure_streaks import Streak
from my_agent_crew.scheduler.jobs import Job
from my_agent_crew.store.runs import RunRecord


def describe_job(
    job: Job,
    last: datetime,
    now: datetime,
    override: bool | None,
    last_run: RunRecord | None,
    running: bool,
    streak: Streak | None,
) -> dict[str, Any]:
    nxt = next_run(job.schedule.cron, job.schedule.every, last, now)
    return {
        **job.to_dict(),
        "enabled": job.schedule.enabled if override is None else override,
        "paused": override is False,
        "next_run": nxt.isoformat(timespec="minutes") if nxt else None,
        "last_run": last_run.to_dict() if last_run else None,
        "running": running,
        # The failures in a row the job is in and when the person was told of them
        # (`failure_streaks.py`); None for a job whose last run did not count as one.
        "failing": streak.to_dict() if streak else None,
    }
