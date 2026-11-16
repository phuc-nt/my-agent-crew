"""Carrying a due job out: the day's cap, which of the four run kinds it needs, then its
check. Split out of `Scheduler` itself only to keep that class within the file's own size
budget. Nothing here sends anything to a channel: a job's report is read on the web."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.scheduler.check import check_failed
from my_agent_crew.scheduler.day_cap import skipped
from my_agent_crew.scheduler.failure_streaks import counts_as_failure
from my_agent_crew.scheduler.jobs import Job, run_command, run_consolidate, run_prompt
from my_agent_crew.scheduler.script_job import run_script_job
from my_agent_crew.store.runs import RunRecord


def job_title(job: Job, clock: Callable[[], datetime]) -> str:
    stamp = clock().strftime("%Y-%m-%d %H:%M")
    return texts.JOB_CONVERSATION_TITLE.format(name=job.schedule.name, stamp=stamp)


async def dispatch(
    job: Job, deps: AgentDeps, hub: ActivityHub, clock: Callable[[], datetime]
) -> RunRecord:
    """Runs the job by its kind."""
    if job.schedule.consolidate:
        return await run_consolidate(job, deps, hub)
    if job.schedule.script:
        return await run_script_job(job, deps, hub, job_title(job, clock))
    if job.schedule.command:
        return await run_command(job, deps, hub, job_title(job, clock))
    return await run_prompt(job, deps, hub, job_title(job, clock))


async def carry_out(
    job: Job, deps: AgentDeps, hub: ActivityHub, clock: Callable[[], datetime]
) -> tuple[RunRecord, bool | None]:
    """A due job from its start to what it came to: the run, then the check the row states,
    and beside the run whether it counts into the job's failures in a row
    (`failure_streaks.py`). Before any of it, the day's cap: a job the day has no money left
    for is not started, and what comes back is the run that says so, beside None, since a
    job that did not run neither failed nor ran well."""
    over = skipped(job, deps, hub, clock, job_title(job, clock))
    if over is not None:
        return over, None
    run = await dispatch(job, deps, hub, clock)
    disagreed = await check_failed(job, deps, hub, run)
    return run, counts_as_failure(run, disagreed)
