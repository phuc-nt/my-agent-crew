"""What one scheduled job actually does, once the clock has decided it is due.

Three kinds, told apart by the schedule: a prompt job opens a fresh autonomous
conversation and runs one turn; a command job runs a shell command with no model at all;
a consolidate job rewrites the agent's `MEMORY.md`. Each ends as a run in the activity
hub, which is how every one of them becomes visible in the UI.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from my_agent_crew.activity import ActivityHub, tracked
from my_agent_crew.agent.events import ToolCallEvent, ToolResultEvent
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.agent.turn_context import JOB
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.memory.consolidate import consolidate_memory
from my_agent_crew.memory.wiki_compile import compile_wiki
from my_agent_crew.skills import Skill, mentioned_skills
from my_agent_crew.store.runs import DONE, FAILED, RunRecord
from my_agent_crew.tools.shell import run_shell

logger = logging.getLogger(__name__)
JOB_SOURCE = "job:"
COMMAND_TIMEOUT_SECONDS = 900
# What a job prompt asks for when there is nothing to tell; such a reply is not pushed.
NOTHING_TO_REPORT = "OK"


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


def prompt_skills(job: Job, skills: Sequence[Skill]) -> list[str]:
    """A job runs with nobody watching, so a skill it names in the prompt is attached even
    when the schedule forgot to list it: the alternative is a run that guesses syntax until
    it hits the step cap."""
    attached = list(job.schedule.skills)
    for name in mentioned_skills(job.schedule.prompt, skills):
        if name not in attached:
            attached.append(name)
    return attached


def nothing_to_report(job: Job, run: RunRecord, deps: AgentDeps) -> bool:
    """A check job told to say only `OK` when all is well has nothing for the person: a
    bare "OK" in the chat every morning is noise that teaches them to skim past the one
    day it says something. The run still shows in the UI; only the push is skipped."""
    if run.status != DONE or run.conversation_id is None:
        return False
    history = deps.store.history(run.conversation_id)
    reply = history[-1].message if history else None
    if reply is None or reply.role != "assistant" or reply.tool_calls:
        return False
    return reply.content.strip().rstrip(".!").strip().upper() == NOTHING_TO_REPORT


async def run_prompt(job: Job, deps: AgentDeps, hub: ActivityHub, title: str) -> RunRecord:
    conv = deps.store.create(
        title=title,
        autonomous=True,
        cost_cap_usd=deps.settings.cost_cap_usd,
        agent_id=job.agent_id,
        skills=prompt_skills(job, deps.skills),
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
    nothing is delivered to a channel and no session summary is written.

    The wiki compile is chained on afterwards rather than given its own cron, because both
    read the same notes and the vault should settle from the same night's reading. It gets
    its own run in the hub, and the consolidation's run is what this returns: the job the
    user asked for is the one whose outcome they are shown.
    """
    source = JOB_SOURCE + job.id
    await consolidate_memory(deps, hub, source=source)
    run = next(iter(hub.recent(1, source=source)), None)
    assert run is not None
    try:
        await compile_wiki(deps, hub)
    except Exception:
        # A failed compile must not take the consolidation down with it: MEMORY.md has
        # already been rewritten by this point, and reporting the whole job as failed
        # would send someone looking for damage that is not there.
        logger.exception("wiki compile failed for %s", job.id)
    return run
