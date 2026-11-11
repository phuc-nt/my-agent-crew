"""Carrying a due job out: which of the four run kinds it needs, then its answer sent on
and its check. Split out of `Scheduler` itself only to keep that class within the file's
own size budget; delivery stays in `runner.py` and is handed in, because an existing test
pins the logger name that records a delivery's outcome."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents.schedule import DELIVERED
from my_agent_crew.scheduler.check import checked
from my_agent_crew.scheduler.jobs import Job, run_command, run_consolidate, run_prompt
from my_agent_crew.scheduler.script_job import run_script_job
from my_agent_crew.store.runs import RunRecord


def job_title(job: Job, clock: Callable[[], datetime]) -> str:
    stamp = clock().strftime("%Y-%m-%d %H:%M")
    return texts.JOB_CONVERSATION_TITLE.format(name=job.schedule.name, stamp=stamp)


async def dispatch(
    job: Job, deps: AgentDeps, hub: ActivityHub, clock: Callable[[], datetime]
) -> tuple[RunRecord, str]:
    """Runs the job by its kind; does not deliver the result — the caller decides that,
    since only an answer of the model's is worth pushing to a channel: a prompt job's, or
    the one a script job asked for. Beside the run stands why it failed, for the caller to
    tell the person, when the job is of a kind that may fail with no conversation to say
    so in: a script, a command, a rewrite of memory. For any other run, nothing."""
    if job.schedule.consolidate:
        return await run_consolidate(job, deps, hub)
    if job.schedule.script:
        return await run_script_job(job, deps, hub, job_title(job, clock))
    if job.schedule.command:
        return await run_command(job, deps, hub, job_title(job, clock))
    return await run_prompt(job, deps, hub, job_title(job, clock)), ""


async def carry_out(
    job: Job,
    deps: AgentDeps,
    hub: ActivityHub,
    clock: Callable[[], datetime],
    deliver: Callable[[Job, RunRecord], Awaitable[None]],
) -> tuple[RunRecord, str]:
    """A due job from its start to what it came to: the run, the answer sent on where the
    job is of a kind that has one, then the check the row states. The check comes after the
    answer, so what the agent said reaches the person as it always did, and a check that
    disagrees is told after it."""
    run, ended_by = await dispatch(job, deps, hub, clock)
    if job.schedule.kind in DELIVERED:
        await deliver(job, run)
    return run, await checked(job, deps, hub, run, ended_by)
