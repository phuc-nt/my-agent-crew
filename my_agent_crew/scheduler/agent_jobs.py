"""Whose the jobs on the clock are: what each agent's file gives it, and what goes when an
agent leaves the crew. `runner.py` decides when a job runs; this module, whom it is for."""

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
