"""Runs each agent's schedules. A prompt job opens a fresh autonomous conversation for
that agent and runs one turn to completion; a command job runs a shell command with no
model at all. Both appear as runs in the activity hub, which is how the UI shows them."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub, tracked
from my_agent_crew.agent.events import ToolCallEvent, ToolResultEvent
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.agent.turn_context import JOB
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.scheduler.cron import due_between, next_run
from my_agent_crew.store.runs import DONE, FAILED, RunRecord
from my_agent_crew.tools.shell import run_shell

logger = logging.getLogger(__name__)
TICK_SECONDS = 20
JOB_SOURCE = "job:"


@dataclass(frozen=True)
class Job:
    id: str  # "<agent_id>/<schedule_id>"
    agent_id: str
    schedule: Schedule

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.schedule.to_dict(),
            "id": self.id,
            "schedule_id": self.schedule.id,
            "agent_id": self.agent_id,
        }


class Scheduler:
    def __init__(
        self,
        agents: dict[str, AgentDeps],
        hub: ActivityHub,
        clock: Callable[[], datetime] = datetime.now,
        deliver: Callable[[str, str], Awaitable[None]] | None = None,
    ):
        self._agents = agents
        self._hub = hub
        self._clock = clock
        self._deliver = deliver
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
            out.append(
                {
                    **job.to_dict(),
                    "next_run": nxt.isoformat(timespec="minutes") if nxt else None,
                    "last_run": last_run.to_dict() if last_run else None,
                    "running": job.id in self._running,
                }
            )
        return out

    # --- ticking -------------------------------------------------------------------------

    def due(self, now: datetime | None = None) -> list[Job]:
        now = now or self._clock()
        return [
            job
            for job in self._jobs.values()
            if job.schedule.enabled
            and job.id not in self._running
            and due_between(job.schedule.cron, job.schedule.every, self._last[job.id], now)
        ]

    async def tick(self, now: datetime | None = None) -> list[RunRecord]:
        now = now or self._clock()
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
            if job.schedule.command:
                return await self._run_command(job, deps)
            return await self._run_prompt(job, deps)
        finally:
            self._running.discard(job.id)

    def _title(self, job: Job) -> str:
        stamp = self._clock().strftime("%Y-%m-%d %H:%M")
        return texts.JOB_CONVERSATION_TITLE.format(name=job.schedule.name, stamp=stamp)

    async def _run_prompt(self, job: Job, deps: AgentDeps) -> RunRecord:
        conv = deps.store.create(
            title=self._title(job),
            autonomous=True,
            cost_cap_usd=deps.settings.cost_cap_usd,
            agent_id=job.agent_id,
        )
        events = run_turn(deps, conv.id, job.schedule.prompt, source=JOB)
        run: RunRecord | None = None
        async for _ in tracked(
            self._hub, events, job.agent_id, JOB_SOURCE + job.id, conv.title, conv.id
        ):
            pass
        for candidate in self._hub.recent(50):
            if candidate.conversation_id == conv.id:
                run = candidate
                break
        assert run is not None
        if self._deliver is not None:
            try:
                await self._deliver(job.agent_id, conv.id)
            except Exception:  # the run itself succeeded; only its delivery did not
                logger.exception("job %s: delivery failed", job.id)
        return run

    async def _run_command(self, job: Job, deps: AgentDeps) -> RunRecord:
        command = job.schedule.command or ""
        run = self._hub.start(job.agent_id, JOB_SOURCE + job.id, self._title(job), None)
        clock = time.monotonic()
        self._hub.record(run, ToolCallEvent("cmd", "shell_run", {"command": command}), clock)
        code, output = await run_shell(command, deps.agent.workspace, timeout_s=900)
        ok = code == 0
        self._hub.record(
            run, ToolResultEvent("cmd", "shell_run", ok, output or f"exit {code}"), time.monotonic()
        )
        self._hub.finish(run, status=DONE if ok else FAILED, summary=(output or "").strip()[-160:])
        return run
