"""The clock over each agent's schedules: which job is due, what ran last, what runs
next. Carrying a job out is `scheduler/jobs.py`; this module only decides when."""

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
from my_agent_crew.scheduler.cron import due_between, next_run
from my_agent_crew.scheduler.jobs import (
    JOB_SOURCE,
    Job,
    run_command,
    run_consolidate,
    run_prompt,
)
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
    ):
        self._agents = agents
        self._hub = hub
        self._clock = clock
        self._deliver = deliver
        self._store = next(iter(agents.values())).store if agents else None
        self._jobs: dict[str, Job] = {}
        self._last: dict[str, datetime] = {}
        self._task: asyncio.Task[None] | None = None
        self._running: set[str] = set()
        self._background: set[asyncio.Task[Any]] = set()
        started = clock()
        for agent_id, deps in agents.items():
            for schedule in deps.agent.schedules:
                job = Job(id=f"{agent_id}/{schedule.id}", agent_id=agent_id, schedule=schedule)
                self._jobs[job.id] = job
                self._last[job.id] = started

    # --- inspection ----------------------------------------------------------------------

    def jobs(self) -> list[Job]:
        return list(self._jobs.values())

    def describe(self) -> list[dict[str, Any]]:
        now = self._clock()
        recent = self._hub.recent(200)
        out = []
        for job in self._jobs.values():
            last_run = next((r for r in recent if r.source == JOB_SOURCE + job.id), None)
            nxt = next_run(job.schedule.cron, job.schedule.every, self._last[job.id], now)
            override = self._override(job)
            out.append(
                {
                    **job.to_dict(),
                    "enabled": job.schedule.enabled if override is None else override,
                    "paused": override is False,
                    "next_run": nxt.isoformat(timespec="minutes") if nxt else None,
                    "last_run": last_run.to_dict() if last_run else None,
                    "running": job.id in self._running,
                }
            )
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
            for job in self._jobs.values()
            if self.enabled(job)
            and job.id not in self._running
            and due_between(job.schedule.cron, job.schedule.every, self._last[job.id], now)
        ]

    async def tick(self, now: datetime | None = None) -> list[RunRecord]:
        now = now or self._clock()
        await expire_overdue(self._agents, self._hub, self._deliver)
        results = []
        for job in self.due(now):
            self._last[job.id] = now
            results.append(await self.run_job(job.id))
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
            return self._jobs[job_id]
        except KeyError as exc:
            raise KeyError(texts.JOB_UNKNOWN.format(job_id=job_id)) from exc

    async def run_job(self, job_id: str) -> RunRecord:
        job = self.get(job_id)
        deps = self._agents[job.agent_id]
        self._running.add(job.id)
        try:
            if job.schedule.consolidate:
                return await run_consolidate(job, deps, self._hub)
            if job.schedule.command:
                return await run_command(job, deps, self._hub, self._title(job))
            run = await run_prompt(job, deps, self._hub, self._title(job))
            await self._deliver_run(job, run)
            return run
        finally:
            self._running.discard(job.id)

    def _title(self, job: Job) -> str:
        stamp = self._clock().strftime("%Y-%m-%d %H:%M")
        return texts.JOB_CONVERSATION_TITLE.format(name=job.schedule.name, stamp=stamp)

    async def _deliver_run(self, job: Job, run: RunRecord) -> None:
        """Pushes the job's answer to the agent's channel; a failed send is logged, not
        raised, because the run itself already succeeded."""
        if self._deliver is None or run.conversation_id is None:
            return
        try:
            delivered = await self._deliver(job.agent_id, run.conversation_id)
        except Exception:
            logger.exception("job %s: delivery failed", job.id)
        else:
            # Without this line a job that answered and a job that stayed silent look
            # identical in the log.
            logger.info(
                "job %s: delivered=%s conv=%s status=%s",
                job.id,
                delivered,
                run.conversation_id,
                run.status,
            )
