"""A schedule's `check`: a command that says whether the job did what it was for.

A job that ends well says only that nothing stopped it. A turn can end on "done" with the
file unwritten, and a command can leave with 0 having synced nothing. So a row may state a
command to run once its own work has ended well. It runs as a command job's command does:
the same shell (`jobs.run_shell`), in the agent's workspace, under the same limit. Leaving
with 0 it changes nothing. Leaving with anything else, or stopped at the limit, it turns the
run into a failed one, summed up in words that say the job ended well and the check
disagreed, and counted into the job's failures in a row (`failure_streaks.py`), turn or no
turn.

Only a run that ended well is checked. One that failed is a failure already, one that was
halted has nothing to check, and one that waits for an approval is taken up later by the
turn that answers it, which no job is behind: such a run is not checked at all.
"""

from __future__ import annotations

import time

from my_agent_crew import texts_job_failure as words
from my_agent_crew.activity import ActivityHub
from my_agent_crew.activity.step_previews import preview
from my_agent_crew.agent.events import ToolCallEvent, ToolResultEvent
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.scheduler import jobs
from my_agent_crew.store.runs import DONE, FAILED, RunRecord

# The id of the check's step in its run, as a command job's own step is "cmd".
STEP = "check"


async def check_failed(job: jobs.Job, deps: AgentDeps, hub: ActivityHub, run: RunRecord) -> bool:
    """Runs the job's check when it states one and its run ended well: whether the check
    is what failed the run."""
    command = job.schedule.check
    if not command or run.status != DONE:
        return False
    hub.record(run, ToolCallEvent(STEP, "shell_run", {"command": command}), time.monotonic())
    code, output = await jobs.run_shell(
        command, deps.agent.workspace, timeout_s=jobs.COMMAND_TIMEOUT_SECONDS
    )
    ok = code == 0
    result = ToolResultEvent(STEP, "shell_run", ok, output or f"exit {code}")
    hub.record(run, result, time.monotonic())
    if ok:
        return False
    why = jobs.command_failure(code, output)
    hub.finish(run, status=FAILED, summary=preview(words.JOB_CHECK_SUMMARY.format(reason=why)))
    return True
