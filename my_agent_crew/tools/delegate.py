"""Handing a whole task to another agent and waiting for its answer.

A delegated task runs as its own conversation, with its own history, budget and activity
run. The child never sees the parent's messages: that is the point — a long task would
otherwise drag the parent's whole context along with it, and the parent gets back one
answer instead of fifty steps of work.

Depth stops at one. An agent may delegate; what it delegates to may not. Two guards say
so, because either alone would be a single edit away from an unbounded fan-out: the child
is handed a registry without this tool, and this tool refuses to run below the top level.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts
from my_agent_crew.activity.tracked import tracked
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.turn_context import (
    DELEGATE,
    tool_call_id,
    turn_conversation_id,
    turn_depth,
)
from my_agent_crew.agents import AgentProfile
from my_agent_crew.agents.approval_ttl import effective_ttl
from my_agent_crew.agents.roster import DELEGATE_TOOL_NAME, delegate_targets
from my_agent_crew.store.models import TOOL, Conversation
from my_agent_crew.tools.delegate_attachments import child_answer, relay_attachments
from my_agent_crew.tools.delegate_open import open_child
from my_agent_crew.tools.delegate_outcome import (
    decide,
    declared_outcome,
    header_line,
    outcome_line,
    relays,
    result_text,
    timed_out,
)
from my_agent_crew.tools.delegate_report import canvas_lines, unfinished_note
from my_agent_crew.tools.registry import Tool, ToolError, ToolResult

if TYPE_CHECKING:  # the runtime builds this tool, so importing it back would be a cycle
    from my_agent_crew.server.runtime import Runtime

__all__ = ["DELEGATE_TOOL_NAME", "MAX_DELEGATES", "build_delegate_tool"]


def _source(parent_id: str) -> str:
    """Which parent conversation delegated this child, so a colliding call id still resolves
    to the right one."""
    return f"{DELEGATE}:{parent_id}"


# How many tasks one conversation may hand out in total. The batch limit only caps a
# single message; without this a model could keep delegating one call at a time until the
# budget ran out.
MAX_DELEGATES = 8
# The child may sit in an approval for the whole TTL before it starts working, so the wait
# has to outlast that by enough to cover the turn that follows.
WAIT_MARGIN_SECONDS = 300.0


def build_delegate_tool(runtime: Runtime, profile: AgentProfile) -> Tool:
    """Delegating to yourself is always allowed: it is how an agent gets a second, clean
    context for a task that would otherwise bloat this one. The targets are fixed when the
    tool is built; the runtime rebuilds it when an agent joins."""
    targets = delegate_targets(profile, {p.id: p for p in runtime.profiles()})
    allowed = (profile.id, *targets)

    async def run(args: dict[str, Any]) -> ToolResult:
        if turn_depth() >= 1:
            raise ToolError(texts.DELEGATE_TOO_DEEP)
        task = str(args.get("task") or "").strip()
        if not task:
            raise ToolError(texts.DELEGATE_PARAM_TASK)
        target = str(args.get("agent") or profile.id)
        if target not in allowed:
            peers = ", ".join(targets) or texts.DELEGATE_NO_PEERS
            raise ToolError(texts.DELEGATE_NOT_ALLOWED.format(target=target, allowed=peers))
        return await _delegate(runtime, profile, target, task, args)

    return Tool(
        name=DELEGATE_TOOL_NAME,
        description=texts.DELEGATE_DESCRIPTION,
        parameters={
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": texts.DELEGATE_PARAM_TASK},
                "agent": {
                    "type": "string",
                    "enum": list(allowed),
                    "description": texts.DELEGATE_PARAM_AGENT,
                },
                "skills": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": texts.DELEGATE_PARAM_SKILLS,
                },
                "relay": {"type": "boolean", "description": texts.DELEGATE_PARAM_RELAY},
            },
            "required": ["task"],
        },
        run=run,
        parallel=True,
    )


async def _delegate(
    runtime: Runtime, profile: AgentProfile, target: str, task: str, args: dict[str, Any]
) -> ToolResult:
    """Opens (or re-finds) the child conversation, runs it, and reports what came back.
    A finished child's answer also rides along whole as `reply`, so the loop can hand it
    to the person without another model call when nothing else happened this turn. The
    canvases the child wrote are named in the result alone, however the wait ended."""
    parent_id = turn_conversation_id()
    parent = runtime.store.get(parent_id) if parent_id else None
    call_id = tool_call_id()
    have_ids = bool(call_id and parent_id)
    child = runtime.store.for_parent_call(call_id, _source(parent_id)) if have_ids else None
    if child is None:
        if len(_children(runtime, parent)) >= MAX_DELEGATES:
            raise ToolError(texts.DELEGATE_TOO_MANY.format(limit=MAX_DELEGATES))
        child = open_child(runtime, parent, target, task, args, call_id)
        runner = _run_child(runtime, child, task, target, parent_id)
        runtime.scheduler.keep(asyncio.create_task(runner))
    # The child's own wait, which it copied from this parent when it opened: a parent whose
    # wait changed since, or the crew's setting, is not what the child's approvals use.
    timeout = effective_ttl(child, runtime.deps_for(target).settings) + WAIT_MARGIN_SECONDS
    run = await runtime.hub.wait_finished(child.id, timeout)
    canvases, more = canvas_lines(runtime.store.artifacts, child.id)
    if run is None:
        latest = runtime.store.runs.latest_for_conversation(child.id)
        return timed_out(child.id, latest, canvases, more)
    try:
        spent = runtime.store.get(child.id).spent_usd
    except KeyError:
        # Deleted from the sidebar while this call waited, which also ends the child's run.
        raise ToolError(texts.DELEGATE_CHILD_DELETED.format(conv_id=child.id)) from None
    if parent is not None:
        # What the child spent is the parent's spend too, or a fan-out would cost the
        # parent's budget nothing and its cap would stop meaning anything.
        runtime.store.add_spend(parent.id, spent)
    said = child_answer(runtime.store.history(child.id))
    decided = runtime.store.approvals.recent(limit=1, conversation_id=child.id, kind=TOOL)
    outcome = decide(run, declared_outcome(said), decided[0] if decided else None)
    note = unfinished_note(run)
    answer = relay_attachments(
        said, runtime.deps_for(target).agent.workspace, profile.workspace, child.id
    )
    body = f"{note}\n\n{answer}" if note else answer
    relay = relays(outcome) and args.get("relay", True) is not False
    output = result_text(header_line(child.id, run), outcome_line(outcome), canvases, more, body)
    return ToolResult(ok=True, output=output, reply=answer if relay else None)


def _children(runtime: Runtime, parent: Conversation | None) -> list[Conversation]:
    """Everything this conversation has already delegated."""
    if parent is None:
        return []
    return runtime.store.delegated_children(parent.id, DELEGATE_TOOL_NAME)


async def _run_child(
    runtime: Runtime, child: Conversation, task: str, agent_id: str, parent_id: str
) -> None:
    """The child runs as its own tracked activity run, so it shows up in the UI on its own
    instead of disappearing inside the parent's single tool call. `parent_id` is the value
    `_delegate` looked the child up with, not read again from context here."""
    deps = runtime.deps_for_child(agent_id)
    source = _source(parent_id or child.id)
    events = run_turn(deps, child.id, task, source=source, depth=1)
    async for _ in tracked(runtime.hub, events, agent_id, source, child.title, child.id):
        pass
