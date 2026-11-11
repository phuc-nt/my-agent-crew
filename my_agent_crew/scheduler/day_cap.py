"""The day's cap on what scheduled jobs may cost.

Each conversation a job opens has a cap of its own (`cost_cap_usd`), which stops one run.
It does not stop the next: a job due every few minutes, or a crew of many, can spend a
day's worth of small runs with nobody watching. `jobs_daily_cost_cap_usd` in `config.yaml`
is the cap over all of them: once the runs of scheduled jobs started today have cost that
much, a job that would call a model is not run for the rest of the day. The two compose by
each doing its own part: a run still stops at its conversation's cap, and the day stops at
this one, so a day spends at most this cap and what the run that crossed it had left.

Today is the home's day (`timezone`), and what was spent is summed from the cost each run
already carries, so a restart changes nothing. A command job calls no model and runs as
ever. A job that is skipped leaves a run that says so, halted with no step, which is what
its row on the jobs page then shows; it is neither a failure nor a recovery, and the count
of a job's failures is left as it was (`failure_streaks.py`). The person is told once a
day, on the channel of the first job skipped that has one.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from my_agent_crew import texts_job_cap as words
from my_agent_crew.activity import ActivityHub
from my_agent_crew.activity.step_previews import preview
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents.schedule import COMMAND
from my_agent_crew.clock import day_start_utc
from my_agent_crew.scheduler.failure_notice import Notify, say
from my_agent_crew.scheduler.jobs import JOB_SOURCE, Job
from my_agent_crew.store.db import now_iso
from my_agent_crew.store.runs import HALTED, RunRecord


class Skipped(str):
    """Why a run ended, when the job was never run: no ending of the job's to count."""


async def skipped(
    job: Job,
    deps: AgentDeps,
    hub: ActivityHub,
    clock: Callable[[], datetime],
    notify: Notify | None,
    title: str,
) -> tuple[RunRecord, Skipped] | None:
    """The run a job is skipped with when the day's cap is reached, or None when the job is
    to run: no cap is set, the job calls no model, or the day has not spent the cap yet."""
    cap = deps.settings.jobs_daily_cost_cap_usd
    if cap <= 0 or job.schedule.kind == COMMAND:
        return None
    now = clock()
    day = now.date()
    since = day_start_utc(day, now.tzinfo or deps.settings.zone)
    spent = deps.store.job_cap.spent(JOB_SOURCE, since)
    if spent < cap:
        return None
    said = {"spent": f"{spent:.2f}", "cap": f"{cap:.2f}"}
    why = words.JOB_CAP_SKIPPED.format(**said)
    run = hub.start(job.agent_id, JOB_SOURCE + job.id, title, None)
    hub.finish(run, status=HALTED, summary=why)
    if not deps.store.job_cap.told(day.isoformat()):
        text = words.JOB_CAP_REACHED.format(name=preview(job.schedule.name), **said)
        # Kept only once the channel took it: a message that got nowhere is tried again
        # with the next job skipped.
        if await say(job, text, notify):
            deps.store.job_cap.tell(day.isoformat(), now_iso())
    return run, Skipped(why)
