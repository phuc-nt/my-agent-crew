"""The job that runs a script, and opens no turn unless the script has something to say.

A check that is due once a week is asked about every morning, and a model told to answer
OK when nothing is due is paid to answer OK. Here the check is a script. It runs the way a
script of `tool_script` runs (`script/tool.py`), over the tools the agent's scripts may
call, whether or not the agent holds that tool, and ends as a run with that one step. A
model is asked there only where the script asks one itself (`script/model_calls.py`), and
that is charged to the run. Only when the script ended well and printed something is a
turn opened, as a prompt job opens one, with the schedule's `then_prompt` and what the
script printed: that turn's run is then the job's, and is what is sent on to the person.

Nobody watches a job and a script waits for nobody, so a call the approval gate would ask
about ends it (`script/gate.py`). It has no conversation either: a tool that works through
one fails there, and what the script keeps (`store`, `load`) is kept under the schedule's
own id, where a script of the turn it opens finds it. What it kept is written before that
turn begins.
"""

from __future__ import annotations

import logging
import time

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.events import NestedCallEvent, ToolCallEvent, ToolResultEvent
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agent.nested_calls import outside_a_turn
from my_agent_crew.agent.turn_context import job_context
from my_agent_crew.scheduler.jobs import JOB_SOURCE, Job, ending, open_turn
from my_agent_crew.script.gate import job_gate
from my_agent_crew.script.model_calls import agents_model
from my_agent_crew.script.scope import SCRIPT_TOOL, writes_too
from my_agent_crew.script.store_session import job_kept
from my_agent_crew.script.tool import run_source
from my_agent_crew.store.runs import DONE, FAILED, RUNNING, RunRecord
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.tools.output_shaping import whole_characters
from my_agent_crew.tools.registry import truncate
from my_agent_crew.tools.result import NestedCall, ToolResult

logger = logging.getLogger(__name__)


async def _carry_out(
    job: Job, deps: AgentDeps, hub: ActivityHub, run: RunRecord
) -> tuple[ToolResult, str]:
    """The script as the one step of `run`: how it ended, and what it printed. Each call
    it makes is listed, and charged where it paid a model, the moment it ends."""
    call_id, source = f"job-{run.id}", job.schedule.script or ""
    hub.record(run, ToolCallEvent(call_id, SCRIPT_TOOL, {"script": source}), time.monotonic())
    told = 0

    def tell(nested: NestedCall) -> None:
        nonlocal told
        hub.record(run, NestedCallEvent(call_id, told, nested.to_dict()), time.monotonic())
        told += 1

    gate = job_gate(deps) if writes_too(deps.settings) else None
    kept = job_kept(deps, job.schedule.id)
    try:
        with job_context(call_id), outside_a_turn(tell):
            result, printed = await run_source(source, deps.tools, gate, kept, agents_model(deps))
    except Exception as exc:  # a bug here fails this job, and the jobs due beside it still run
        logger.exception("script job %s crashed", job.id)
        failed = TOOL_FAILED.format(error=type(exc).__name__)
        result, printed = ToolResult(ok=False, output=failed), ""
    # Whole characters, as a tool's answer is made before it is stored or sent on.
    said, printed = whole_characters(result.output), whole_characters(printed)
    closing = ToolResultEvent(
        tool_call_id=call_id,
        name=SCRIPT_TOOL,
        ok=result.ok,
        output=said,
        calls=[nested.to_dict() for nested in result.calls],
        received_chars=result.received_chars,
        printed_chars=result.printed_chars,
    )
    hub.record(run, closing, time.monotonic())
    hub.finish(
        run, status=DONE if result.ok else FAILED, summary=ending(printed if result.ok else said)
    )
    return result, printed


async def run_script_job(job: Job, deps: AgentDeps, hub: ActivityHub, title: str) -> RunRecord:
    """The run the job comes to: the script's own, or that of the turn opened for what it
    printed. A script that failed, or printed nothing, opens no turn."""
    run = hub.start(job.agent_id, JOB_SOURCE + job.id, title, None)
    try:
        result, printed = await _carry_out(job, deps, hub, run)
    finally:
        if run.status == RUNNING:  # stopped short: closed as a turn's run is (`tracked.py`)
            hub.interrupt(run)
    then_prompt = job.schedule.then_prompt
    if not (result.ok and printed.strip() and then_prompt):
        return run
    handed = truncate(printed, deps.settings.tool_output_chars)
    # One blank line between the two: a prompt written as a block of the file ends on one.
    return await open_turn(job, deps, hub, title, f"{then_prompt.rstrip()}\n\n{handed}")
