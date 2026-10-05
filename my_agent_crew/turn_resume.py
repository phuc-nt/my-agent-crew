"""Taking up the turns a restart cut.

A turn lives in one process: its run is a task, and the task dies with the server. What
the turn had done is in the message log, so the server that starts next can carry it on.
The hub closed every run the previous process was still working on and kept the ones never
taken up before (`store/run_restart.py`); each of those that may still go on is reopened as
the same run and read to its end by whoever reads that kind of turn — the bot for a chat's,
the scheduler's delivery for a job's, the server itself for the rest.

A run is taken up once. Reopening it writes that down before the turn takes a step, so a
turn that brings the server down again is closed at the next start instead of being tried
for ever. One left alone here stays closed as interrupted, and the next message in its
conversation finds the log as any interrupted turn leaves it.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from my_agent_crew.activity.tracked import tracked
from my_agent_crew.agent.events import Event
from my_agent_crew.agent.replay import continue_cut_turn
from my_agent_crew.agent.turn_context import DELEGATE, JOB, TELEGRAM, normalize_source
from my_agent_crew.store.models import AWAITING_APPROVAL
from my_agent_crew.store.runs import RunRecord

if TYPE_CHECKING:
    from my_agent_crew.server.runtime import Runtime

logger = logging.getLogger(__name__)


def resume_cut_turns(runtime: Runtime) -> list[RunRecord]:
    """Starts the rest of every cut turn that may have one, and returns their runs. Called
    once, when the server starts, before anything else begins a turn."""
    cut, runtime.hub.cut = runtime.hub.cut, []
    going: dict[str, RunRecord] = {}
    # A delegated task goes on only with the turn that waits for it, so that turn is first.
    for run in sorted(cut, key=lambda run: normalize_source(run.source) == DELEGATE):
        left = _left_alone(runtime, run, going)
        if left:
            logger.info("run %s: not taken up after the restart: %s", run.id, left)
            continue
        _take_up(runtime, run)
        going[run.conversation_id or ""] = run
        logger.info("run %s: taken up after the restart", run.id)
    return list(going.values())


def _left_alone(runtime: Runtime, run: RunRecord, going: dict[str, RunRecord]) -> str:
    """Why this run stays closed; empty when it is taken up."""
    conv_id = run.conversation_id or ""
    try:
        conv = runtime.store.get(conv_id)
    except KeyError:
        return "its conversation is gone"
    if conv.status == AWAITING_APPROVAL or runtime.store.approvals.pending(conv_id) is not None:
        return "it waits on a decision, whose turn carries on from there"
    if conv.over_budget:
        return "its conversation has spent its budget"
    latest = runtime.store.runs.latest_for_conversation(conv_id)
    if latest is None or latest.id != run.id:
        return "a later run took its place"
    kind = normalize_source(run.source)
    if kind == DELEGATE and run.source.partition(":")[2] not in going:
        return "the turn that delegated it is not going on"
    if kind == TELEGRAM and not (runtime.channel is not None and runtime.channel_live):
        return "no bot is up to answer it"
    return ""


def _take_up(runtime: Runtime, run: RunRecord) -> None:
    conv_id = run.conversation_id or ""
    kind = normalize_source(run.source)
    deps = runtime.deps_for_conversation(conv_id)
    if kind == DELEGATE:
        deps = runtime.deps_for_child(deps.agent.id)
    hub = runtime.hub
    hub.reopen(run)
    hub.turn_starting(conv_id)
    rest = continue_cut_turn(deps, conv_id, kind)
    events = tracked(hub, rest, run.agent_id, run.source, run.title, conv_id)
    if kind == TELEGRAM and runtime.channel is not None:
        task = runtime.channel.spawn(runtime.channel.reply_to(events, conv_id))
    else:
        if kind == JOB:
            events = _then_delivered(runtime, run, events)
        task = runtime.inbound.host.read(conv_id, events)

    def let_go(_: object) -> None:
        # A reader that ended before the turn took a step left the run as it was reopened.
        if hub.holding(run):
            hub.interrupt(run)

    task.add_done_callback(let_go)


async def _then_delivered(
    runtime: Runtime, run: RunRecord, events: AsyncIterator[Event]
) -> AsyncIterator[Event]:
    """A job's turn, its answer pushed to the chat when it ends as the scheduler would have
    pushed it. A job removed meanwhile has nobody to tell."""
    async for event in events:
        yield event
    try:
        job = runtime.scheduler.get(run.source.partition(":")[2])
    except KeyError:
        return
    await runtime.scheduler.deliver_run(job, run)
