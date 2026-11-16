"""The clock over each agent's schedules: which job is due, what ran last, what runs next.
Carrying a job out is `scheduler/jobs.py`; this decides when, and counts what each run came
to. A job tells no channel: its report and its failures are read on the web."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.approval_expiry import Deliver, expire_overdue
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.scheduler.cron import due_between
from my_agent_crew.scheduler.describe import describe_job
from my_agent_crew.scheduler.execute import carry_out
from my_agent_crew.scheduler.failure_streaks import Streaks
from my_agent_crew.scheduler.jobs import JOB_SOURCE, Job
from my_agent_crew.scheduler.table import JobTable
from my_agent_crew.store.db import now_iso
from my_agent_crew.store.runs import RunRecord

logger = logging.getLogger(__name__)
TICK_SECONDS = 20


class Scheduler:
    def __init__(
        self,
        agents: dict[str, AgentDeps],
        hub: ActivityHub,
        clock: Callable[[], datetime] = datetime.now,
        deliver: Deliver | None = None,
    ):
        """`deliver` sends on the answer of a turn resumed because its request ran out, where
        its conversation wants it (`approval_expiry.py`); a job's own answer is never sent."""
        self._agents, self._hub, self._clock = agents, hub, clock
        self._deliver = deliver
        self._store = next(iter(agents.values())).store if agents else None
        self._jobs = JobTable(agents, self._store, clock)
        self._streaks = Streaks(self._store, self._jobs.rows())
        self._task: asyncio.Task[None] | None = None
        self._running: set[str] = set()
        self._background: set[asyncio.Task[Any]] = set()

    # --- inspection ----------------------------------------------------------------------

    def jobs(self) -> list[Job]:
        return list(self._jobs.rows().values())

    def forget_agent(self, agent_id: str) -> None:
        """An agent that leaves the crew takes its jobs off the clock with it, and what was
        counted of their failures; a page open on the list is told to read it again."""
        self._jobs.forget_agent(agent_id)
        self._streaks.forget_agent(agent_id)
        self._hub.publish_jobs()

    def reload_profiles(self) -> None:
        """Puts on the clock what the crew's files state now, with no restart, and has every
        page open on the list read it again: called when an agent joined the crew or was
        saved. A job no file states any more leaves no count of failures to its id."""
        for job_id in self._jobs.reload():
            self._streaks.forget(job_id)
        self._hub.publish_jobs()

    def describe(self) -> list[dict[str, Any]]:
        now = self._clock()
        out = []
        for job in self._jobs.rows().values():
            # Asked per job: a weekly job's last run sits far behind a busy crew's week.
            last_run = next(iter(self._hub.recent(1, source=JOB_SOURCE + job.id)), None)
            last, running = self._jobs.last[job.id], job.id in self._running
            failing = self._streaks.of(job.id)
            row = describe_job(job, last, now, self._override(job), last_run, running, failing)
            out.append(row)
        return out

    # --- switching -----------------------------------------------------------------------

    def _override(self, job: Job) -> bool | None:
        return self._store.jobs.enabled(job.id) if self._store else None

    def enabled(self, job: Job) -> bool:
        """The profile decides unless the person flipped the job from the UI."""
        override = self._override(job)
        return job.schedule.enabled if override is None else override

    def set_enabled(self, job_id: str, enabled: bool) -> None:
        job = self.get(job_id)
        if self._store is not None:
            self._store.jobs.set_enabled(job.id, enabled, now_iso())

    # --- ticking -------------------------------------------------------------------------

    def due(self, now: datetime | None = None) -> list[Job]:
        now = now or self._clock()
        return [
            job
            for job in self._jobs.rows().values()
            if self.enabled(job)
            and job.id not in self._running
            and due_between(job.schedule.cron, job.schedule.every, self._jobs.last[job.id], now)
        ]

    async def tick(self, now: datetime | None = None) -> list[RunRecord]:
        now = now or self._clock()
        await expire_overdue(self._agents, self._hub, self._deliver)
        results = []
        for job in self.due(now):
            if job.agent_id in self._agents and self._jobs.rows().get(job.id) != job:
                # Saved or taken away while an earlier job of this tick ran: what was judged
                # due is not what the clock holds now, and the next tick judges that.
                continue
            self._jobs.last[job.id] = now
            if job.agent_id in self._agents:
                results.append(await self.run_job(job.id))
                continue
            # Its agent left while an earlier job of this tick ran, or by a way that took no
            # job along. Told of once: the job goes with the line, and the tick goes on.
            logger.warning("job %s: agent %s is not in the crew, job dropped", job.id, job.agent_id)
            self._jobs.drop(job.id)
            self._streaks.forget(job.id)
        return results

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        for task in list(self._background):
            task.cancel()

    def keep(self, task: asyncio.Task[Any]) -> None:
        """Hold a reference to a run started from the API so it is not garbage-collected."""
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:  # a broken job must not stop the clock
                logger.exception("scheduler tick failed")
            await asyncio.sleep(TICK_SECONDS)

    # --- running -------------------------------------------------------------------------

    def get(self, job_id: str) -> Job:
        try:
            return self._jobs.rows()[job_id]
        except KeyError as exc:
            raise KeyError(texts.JOB_UNKNOWN.format(job_id=job_id)) from exc

    async def run_job(self, job_id: str) -> RunRecord:
        job = self.get(job_id)
        deps = self._agents[job.agent_id]
        self._running.add(job.id)
        try:
            run, failed = await carry_out(job, deps, self._hub, self._clock)
            # What the job came to, for the log: its report is read on the web, not sent.
            logger.info("job %s: status=%s conv=%s", job.id, run.status, run.conversation_id)
            # A job that left the clock while it ran is counted no more: what it came to
            # would be held against whichever job is later made under its id.
            if failed is not None and job.id in self._jobs.rows():
                before = self._streaks.of(job.id)
                self._streaks.settle(job.id, failed, self._clock())
                # The page read the job's row when the run ended, which is before this.
                if self._streaks.of(job.id) != before:
                    self._hub.publish_jobs()
            return run
        finally:
            self._running.discard(job.id)
