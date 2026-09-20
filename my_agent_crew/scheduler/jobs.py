"""What one scheduled job actually does, once the clock has decided it is due.

Three kinds, told apart by the schedule: a prompt job opens a fresh autonomous
conversation and runs one turn; a command job runs a shell command with no model at all;
a consolidate job rewrites the agent's `MEMORY.md`. Each ends as a run in the activity
hub, which is how every one of them becomes visible in the UI.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from my_agent_crew.activity import ActivityHub, tracked
from my_agent_crew.agent.events import ToolCallEvent, ToolResultEvent
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.agent.turn_context import JOB
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.memory.consolidate import JOB_SOURCE as CONSOLIDATE_SOURCE
from my_agent_crew.memory.consolidate import consolidate_memory
from my_agent_crew.store.runs import DONE, FAILED, RunRecord
from my_agent_crew.tools.shell import run_shell

logger = logging.getLogger(__name__)
JOB_SOURCE = "job:"
COMMAND_TIMEOUT_SECONDS = 900


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


async def run_prompt(job: Job, deps: AgentDeps, hub: ActivityHub, title: str) -> RunRecord:
    conv = deps.store.create(
        title=title,
        autonomous=True,
        cost_cap_usd=deps.settings.cost_cap_usd,
        agent_id=job.agent_id,
    )
    events = run_turn(deps, conv.id, job.schedule.prompt, source=JOB)
    async for _ in tracked(hub, events, job.agent_id, JOB_SOURCE + job.id, conv.title, conv.id):
        pass
    run = next((r for r in hub.recent(50) if r.conversation_id == conv.id), None)
    assert run is not None
    return run


async def run_command(job: Job, deps: AgentDeps, hub: ActivityHub, title: str) -> RunRecord:
    command = job.schedule.command or ""
    run = hub.start(job.agent_id, JOB_SOURCE + job.id, title, None)
    clock = time.monotonic()
    hub.record(run, ToolCallEvent("cmd", "shell_run", {"command": command}), clock)
    code, output = await run_shell(command, deps.agent.workspace, timeout_s=COMMAND_TIMEOUT_SECONDS)
    ok = code == 0
    hub.record(
        run, ToolResultEvent("cmd", "shell_run", ok, output or f"exit {code}"), time.monotonic()
    )
    hub.finish(run, status=DONE if ok else FAILED, summary=(output or "").strip()[-160:])
    return run


async def run_consolidate(job: Job, deps: AgentDeps, hub: ActivityHub) -> RunRecord:
    """Rewriting MEMORY.md is its own kind of run: one model call and no conversation, so
    nothing is delivered to a channel and no session summary is written."""
    await consolidate_memory(deps, hub)
    run = next((r for r in hub.recent(20) if r.source == CONSOLIDATE_SOURCE), None)
    assert run is not None
    return run
