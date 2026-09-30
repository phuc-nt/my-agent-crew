"""Picking which of the three run kinds a due job needs. Split out of `Scheduler` itself
only to keep that class within the file's own size budget; delivery stays in `runner.py`
because an existing test pins the logger name that records a delivery's outcome."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.scheduler.jobs import Job, run_command, run_consolidate, run_prompt
from my_agent_crew.store.runs import RunRecord


def job_title(job: Job, clock: Callable[[], datetime]) -> str:
    stamp = clock().strftime("%Y-%m-%d %H:%M")
    return texts.JOB_CONVERSATION_TITLE.format(name=job.schedule.name, stamp=stamp)


async def dispatch(
    job: Job, deps: AgentDeps, hub: ActivityHub, clock: Callable[[], datetime]
) -> RunRecord:
    """Runs the job by its kind; does not deliver the result — the caller decides that,
    since only a prompt job's answer is worth pushing to a channel."""
    if job.schedule.consolidate:
        return await run_consolidate(job, deps, hub)
    if job.schedule.command:
        return await run_command(job, deps, hub, job_title(job, clock))
    return await run_prompt(job, deps, hub, job_title(job, clock))
