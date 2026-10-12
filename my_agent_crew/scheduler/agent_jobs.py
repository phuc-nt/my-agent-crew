"""Whose the jobs on the clock are: what each agent's file gives it, which of those begin
again when a file is saved, and what goes when an agent leaves the crew. `runner.py` decides
when a job runs; this module, whom it is for."""

from __future__ import annotations

from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.scheduler.jobs import Job
from my_agent_crew.store.db import Store


def profile_jobs(agents: dict[str, AgentDeps]) -> dict[str, Job]:
    """Every schedule the crew's files state, keyed `<agent_id>/<schedule_id>`."""
    jobs: dict[str, Job] = {}
    for agent_id, deps in agents.items():
        for schedule in deps.agent.schedules:
            job = Job(id=f"{agent_id}/{schedule.id}", agent_id=agent_id, schedule=schedule)
            jobs[job.id] = job
    return jobs


def starts_afresh(held: Job | None, stated: Job) -> bool:
    """Whether a job a file states now is judged from this moment on, and not from the mark
    the clock kept under its id: a job the clock did not hold, one whose timing is another,
    or one its file had switched off and switches on. The mark of such a job is that of a
    row that is no more, and judged from it the job would run at once for a time that
    passed under the row before it. A save of what the job does, or of what it is called,
    leaves its timing as it was, and so its mark: the job still runs when it was going to."""
    if held is None:
        return True
    was, now = held.schedule, stated.schedule
    return (was.cron, was.every) != (now.cron, now.every) or (now.enabled and not was.enabled)


def forget_agent(held: dict[str, Job], store: Store | None, agent_id: str) -> None:
    """Takes an agent's jobs away with it: out of `held` those its file gave it, and out of
    the store those it was given in a conversation and every switch flipped on a job of its.

    Left where they were, the first kind came due with nobody to run them, and all three
    waited for an agent to be made under the id: the jobs would have run again as that
    agent, switched as the one before it left them."""
    for job_id, job in list(held.items()):
        if job.agent_id == agent_id:
            held.pop(job_id, None)
    if store is not None:
        store.created_schedules.forget_agent(agent_id)
        store.jobs.forget_agent(agent_id)
