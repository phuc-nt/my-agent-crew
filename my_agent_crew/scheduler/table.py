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
        # Profile schedules only, as the crew's files stated them when last read: at the
        # start, and again whenever an agent joins the crew or is saved (`reload`).
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

    def reload(self) -> list[str]:
        """Reads the profile schedules again from the crew as it stands, and returns the
        ids of the jobs no file states any more. Called on the event loop, as `tick()` is.

        A job that is new, or whose timing the save changed, is judged from now on
        (`agent_jobs.starts_afresh`); every other keeps the mark it had. A job that is gone
        takes its switch out of the store with it, so one later stated under its id is not
        paused by a switch nobody flipped on it. Its mark stays: a reader on another
        thread may still hold the table that names it, and looks its mark up by id."""
        held, stated = self._profile, agent_jobs.profile_jobs(self._agents)
        now = self._clock()
        for job_id, job in stated.items():
            if agent_jobs.starts_afresh(held.get(job_id), job):
                # Set, where `rows` only fills in: an id that was on the clock before has
                # left its mark here, and that mark is what must not be judged from.
                self.last[job_id] = now
        # Put in place of the old dict, which is never changed for this: `rows` may be
        # reading it on a thread-pool thread.
        self._profile = stated
        gone = [job_id for job_id in held if job_id not in stated]
        for job_id in gone:
            if self._store is not None:
                self._store.jobs.clear(job_id)
        return gone

    def drop(self, job_id: str) -> None:
        """Takes one profile job off the clock; a chat-created one goes with its row."""
        self._profile.pop(job_id, None)

    def forget_agent(self, agent_id: str) -> None:
        """An agent that leaves the crew takes its jobs off the clock with it. Called on the
        event loop, as `tick()` is."""
        agent_jobs.forget_agent(self._profile, self._store, agent_id)
