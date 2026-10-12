"""The clock over each agent's schedules: which job is due, what ran last, what runs
next. Carrying a job out is `scheduler/jobs.py`; this module only decides when, and has the
person told of what a job came to."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.approval_expiry import expire_overdue
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents.schedule import DELIVERED
from my_agent_crew.scheduler.cron import due_between
from my_agent_crew.scheduler.describe import describe_job
from my_agent_crew.scheduler.execute import dispatch
from my_agent_crew.scheduler.failure_notice import Notify
from my_agent_crew.scheduler.failure_streaks import Streaks
from my_agent_crew.scheduler.jobs import JOB_SOURCE, Job, nothing_to_report
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
        deliver: Callable[[str, str], Awaitable[bool]] | None = None,
        notify: Notify | None = None,
    ):
        self._agents = agents
        self._hub = hub
        self._clock = clock
        self._deliver = deliver
        self._store = next(iter(agents.values())).store if agents else None
        self._jobs = JobTable(agents, self._store, clock)
        self._streaks = Streaks(notify, clock)
        self._task: asyncio.Task[None] | None = None
        self._running: set[str] = set()
        self._background: set[asyncio.Task[Any]] = set()

    # --- inspection ----------------------------------------------------------------------

    def jobs(self) -> list[Job]:
        return list(self._jobs.rows().values())

    def forget_agent(self, agent_id: str) -> None:
        """An agent that leaves the crew takes its jobs off the clock with it, and what was
        counted of their failures. Called on the event loop, as `tick()` is."""
        self._jobs.forget_agent(agent_id)
        self._streaks.forget_agent(agent_id)

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
            run, ended_by = await dispatch(job, deps, self._hub, self._clock)
            if job.schedule.kind in DELIVERED:
                await self.deliver_run(job, run)
            # A job that left the clock while it ran is counted no more: what it came to
            # would be held against whichever job is later made under its id.
            if job.id in self._jobs.rows():
                await self._streaks.settle(job, run, ended_by)
            return run
        finally:
            self._running.discard(job.id)

    async def deliver_run(self, job: Job, run: RunRecord) -> None:
        """Pushes the job's answer to the agent's channel; a failed send is logged, not
        raised, because the run itself already succeeded."""
        deps = self._agents.get(job.agent_id)
        if self._deliver is None or run.conversation_id is None or deps is None:
            return
        if nothing_to_report(job, run, deps):
            logger.info("job %s: nothing to report, not delivered", job.id)
            return
        try:
            delivered = await self._deliver(job.agent_id, run.conversation_id)
        except Exception:
            logger.exception("job %s: delivery failed", job.id)
        else:
            # Without this line a job that answered and a job that stayed silent look
            # identical in the log.
            conv, status = run.conversation_id, run.status
            logger.info("job %s: delivered=%s conv=%s status=%s", job.id, delivered, conv, status)
