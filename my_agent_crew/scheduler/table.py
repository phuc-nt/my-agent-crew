"""The jobs on the clock, and the moment each was last judged. `runner.py` asks this which
jobs there are and decides which of them is due; `agent_jobs.py` says whose a job is."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.scheduler import agent_jobs
from my_agent_crew.scheduler.created import chat_jobs
from my_agent_crew.scheduler.jobs import Job
from my_agent_crew.store.db import Store


class JobTable:
    def __init__(
        self, agents: dict[str, AgentDeps], store: Store | None, clock: Callable[[], datetime]
    ):
        self._agents, self._store, self._clock = agents, store, clock
        # Profile schedules only, as the files stated them at the start: an edit of them
        # asks for a restart, so these are never rebuilt, only dropped with their agent.
        # Chat-created jobs are never kept here — `rows` reads them fresh from the store
        # on every call instead, since a person approving or deleting one runs on a FastAPI
        # thread-pool thread while `tick()` runs on the event loop, and an in-memory dict
        # updated from both would race.
        self._profile = agent_jobs.profile_jobs(agents)
        # Up to when each job has been judged: what came due after it is still to run.
        self.last = dict.fromkeys(self._profile, clock())

    def rows(self) -> dict[str, Job]:
        """The full job table for this instant: profile schedules plus every chat-created
        row whose agent still exists. Rebuilt on every call rather than cached, so an
        approval or a deletion takes effect the moment it lands in the store, with no
        restart and no separate signal to tell the scheduler to look again.

        A job seen here for the first time is given a `last` of "now" via `setdefault`:
        `last` only ever grows, never shrinks, so two threads racing on the same new key
        settle on the same value either way, and an existing key is never overwritten by a
        second, later `setdefault` call that would otherwise reset its due time."""
        table = {**self._profile, **chat_jobs(self._store, self._agents)}
        now = self._clock()
        for job_id in table:
            self.last.setdefault(job_id, now)
        return table

    def drop(self, job_id: str) -> None:
        """Takes one profile job off the clock; a chat-created one goes with its row."""
        self._profile.pop(job_id, None)

    def forget_agent(self, agent_id: str) -> None:
        """An agent that leaves the crew takes its jobs off the clock with it. Called on the
        event loop, as `tick()` is."""
        agent_jobs.forget_agent(self._profile, self._store, agent_id)
