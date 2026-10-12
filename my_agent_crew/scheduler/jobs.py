"""What one scheduled job actually does, once the clock has decided it is due.

Four kinds, told apart by the schedule: a prompt job opens a fresh autonomous
conversation and runs one turn; a command job runs a shell command with no model at all;
a script job runs a script as `tool_script` would, and opens such a turn only when the
script printed something to hand on (`script_job.py`); a consolidate job rewrites the
agent's `MEMORY.md`. Each ends as a run in the activity hub, which is how every one of
them becomes visible in the UI. The two that never open a conversation hand on, beside
their run, why it failed, for the person to be told (`failure_notice.py`).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from my_agent_crew import texts
from my_agent_crew import texts_job_failure as words
from my_agent_crew.activity import ActivityHub, tracked
from my_agent_crew.activity.step_previews import CUT, PREVIEW_CHARS
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
    # "profile" for a job from `agent.yaml`, "chat" for one an agent proposed and a person
    # approved. The UI uses this to label a job and to decide whether it may be deleted.
    origin: str = "profile"

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.schedule.to_dict(),
            "id": self.id,
            "schedule_id": self.schedule.id,
            "agent_id": self.agent_id,
            "origin": self.origin,
        }


def ending(text: str) -> str:
    """The end of what a job with no model said, which is what its run is summed up by. A
    text longer than a summary keeps opens on the mark of a cut: its end alone would begin
    in the middle of a word, with nothing to say more came before."""
    text = text.strip()
    return text if len(text) <= PREVIEW_CHARS else CUT + text[-PREVIEW_CHARS:]


def prompt_skills(job: Job, skills: Sequence[Skill]) -> list[str]:
    """A job runs with nobody watching, so a skill it names in the prompt is attached even
    when the schedule forgot to list it: the alternative is a run that guesses syntax until
    it hits the step cap. The prompt of a script job is the one its output is handed to."""
    attached = list(job.schedule.skills)
    said = job.schedule.prompt or job.schedule.then_prompt or ""
    for name in mentioned_skills(said, skills):
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
    return await open_turn(job, deps, hub, title, job.schedule.prompt)


async def open_turn(
    job: Job, deps: AgentDeps, hub: ActivityHub, title: str, message: str | None
) -> RunRecord:
    """One turn nobody watches, in a conversation opened for it, and the run it left. What
    a prompt job is; a script job opens one the same way for what its script printed."""
    conv = deps.store.create(
        title=title,
        autonomous=True,
        cost_cap_usd=deps.settings.cost_cap_usd,
        agent_id=job.agent_id,
        skills=prompt_skills(job, deps.skills),
        approval_ttl_seconds=job.schedule.approval_ttl_seconds,
    )
    events = run_turn(deps, conv.id, message, source=JOB)
    async for _ in tracked(hub, events, job.agent_id, JOB_SOURCE + job.id, conv.title, conv.id):
        pass
    run = next((r for r in hub.recent(50) if r.conversation_id == conv.id), None)
    assert run is not None
    return run


def command_failure(code: int | None, output: str) -> str:
    """Why a command job failed, as the person is told it: the code the command left with
    and the last line it printed, which is where a command says what went wrong; or, with
    no code, that it ran past its limit and was stopped, in the shell tool's own words."""
    if code is None:
        return texts.SHELL_TIMEOUT.format(seconds=COMMAND_TIMEOUT_SECONDS)
    exited = words.COMMAND_EXITED.format(code=code)
    last = next((line.strip() for line in reversed(output.splitlines()) if line.strip()), "")
    return f"{exited} {words.COMMAND_LAST_LINE.format(line=last)}" if last else exited


async def run_command(
    job: Job, deps: AgentDeps, hub: ActivityHub, title: str
) -> tuple[RunRecord, str]:
    """The run of the command, and beside it why it failed when it did."""
    command = job.schedule.command or ""
    run = hub.start(job.agent_id, JOB_SOURCE + job.id, title, None)
    clock = time.monotonic()
    hub.record(run, ToolCallEvent("cmd", "shell_run", {"command": command}), clock)
    code, output = await run_shell(command, deps.agent.workspace, timeout_s=COMMAND_TIMEOUT_SECONDS)
    ok = code == 0
    hub.record(
        run, ToolResultEvent("cmd", "shell_run", ok, output or f"exit {code}"), time.monotonic()
    )
    hub.finish(run, status=DONE if ok else FAILED, summary=ending(output or ""))
    return run, "" if ok else command_failure(code, output)


async def run_consolidate(job: Job, deps: AgentDeps, hub: ActivityHub) -> tuple[RunRecord, str]:
    """Rewriting MEMORY.md is its own kind of run: one model call and no conversation, so
    nothing is delivered to a channel and no session summary is written.

    The wiki compile is chained on afterwards rather than given its own cron, because both
    read the same notes and the vault should settle from the same night's reading. It gets
    its own run in the hub, and the consolidation's run is what this returns: the job the
    user asked for is the one whose outcome they are shown.

    Beside the run stands why it failed when it did, which is what the run was summed up
    by. A rewrite that raised has closed its run as failed before raising, and that run is
    what comes back, with no compile after it: the person is told of it as of any failed
    job, and the clock goes on to the jobs due after this one.
    """
    source = JOB_SOURCE + job.id
    seen = {earlier.id for earlier in hub.recent(1, source=source)}
    try:
        await consolidate_memory(deps, hub, source=source)
    except Exception:
        # Only a run this rewrite opened and closed as failed is its own to be told by: one
        # that raised before it had a run leaves the job's last run an earlier night's.
        failed = next((r for r in hub.recent(1, source=source) if r.id not in seen), None)
        if failed is None or failed.status != FAILED:
            raise
        return failed, failed.summary
    run = next(iter(hub.recent(1, source=source)), None)
    assert run is not None
    try:
        await compile_wiki(deps, hub)
    except Exception:
        # A failed compile must not take the consolidation down with it: MEMORY.md has
        # already been rewritten by this point, and reporting the whole job as failed
        # would send someone looking for damage that is not there.
        logger.exception("wiki compile failed for %s", job.id)
    return run, run.summary if run.status == FAILED else ""
