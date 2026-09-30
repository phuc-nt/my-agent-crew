"""Turns a chat-approved row into the same `Job` shape a profile schedule already is, so
the scheduler never needs to know which source a job came from once it has one.

A row is read fresh on every scheduler tick (`Scheduler._table`, not here) rather than
cached in memory: the approval that creates it, and the DELETE route that removes it, both
run on a FastAPI thread-pool thread while `tick()` runs on the event loop, and the store
is the only thing both sides agree on without a lock shared across them."""

from __future__ import annotations

from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.scheduler.jobs import Job
from my_agent_crew.store.created_schedules import CreatedScheduleRow
from my_agent_crew.store.db import Store

CHAT = "chat"


def to_schedule(row: CreatedScheduleRow) -> Schedule:
    """Always enabled at the profile level: a chat schedule has no yaml default to fall
    back to, and `job_state`'s own override is what a runtime pause actually uses. Never a
    command or a consolidation — a person approved a prompt, not a shell line, and a chat
    schedule cannot touch `MEMORY.md` at all. `skills` is kept even when a name in it no
    longer resolves: `prompt_skills` already treats an unknown skill as simply absent."""
    return Schedule(
        id=row.id,
        name=row.name,
        cron=row.cron,
        every=row.every,
        prompt=row.prompt,
        enabled=True,
        skills=row.skills,
    )


def chat_jobs(store: Store | None, agents: dict[str, AgentDeps]) -> dict[str, Job]:
    """Every chat-created row whose agent still exists, keyed the same way a profile job
    is: `<agent_id>/<schedule_id>`. A row for an agent that was since removed from the
    crew is silently dropped rather than surfaced as an error — `Scheduler.run_job` does
    an unguarded lookup into `agents`, so a row this function let through must be one that
    lookup can actually resolve."""
    if store is None:
        return {}
    out: dict[str, Job] = {}
    for row in store.created_schedules.all():
        if row.agent_id not in agents:
            continue
        job_id = f"{row.agent_id}/{row.id}"
        out[job_id] = Job(id=job_id, agent_id=row.agent_id, schedule=to_schedule(row), origin=CHAT)
    return out
