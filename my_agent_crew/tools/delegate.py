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
from my_agent_crew.activity.hub import tracked
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.turn_context import (
    DELEGATE,
    tool_call_id,
    turn_conversation_id,
    turn_depth,
)
from my_agent_crew.agents import AgentProfile
from my_agent_crew.store.models import Conversation
from my_agent_crew.tools.registry import Tool, ToolError

if TYPE_CHECKING:  # the runtime builds this tool, so importing it back would be a cycle
    from my_agent_crew.server.runtime import Runtime

DELEGATE_TOOL_NAME = "delegate"
TITLE_TASK_CHARS = 60
# How many tasks one conversation may hand out in total. The batch limit only caps a
# single message; without this a model could keep delegating one call at a time until the
# budget ran out.
MAX_DELEGATES = 8
# The child may sit in an approval for the whole TTL before it starts working, so the wait
# has to outlast that by enough to cover the turn that follows.
WAIT_MARGIN_SECONDS = 300.0


def build_delegate_tool(runtime: Runtime, profile: AgentProfile) -> Tool:
    """Delegating to yourself is always allowed: it is how an agent gets a second, clean
    context for a task that would otherwise bloat this one."""
    allowed = (profile.id, *profile.delegates)

    async def run(args: dict[str, Any]) -> str:
        if turn_depth() >= 1:
            raise ToolError(texts.DELEGATE_TOO_DEEP)
        task = str(args.get("task") or "").strip()
        if not task:
            raise ToolError(texts.DELEGATE_PARAM_TASK)
        target = str(args.get("agent") or profile.id)
        if target not in allowed:
            peers = ", ".join(profile.delegates) or texts.DELEGATE_NO_PEERS
            raise ToolError(texts.DELEGATE_NOT_ALLOWED.format(target=target, allowed=peers))
        return await _delegate(runtime, target, task, args)

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
            },
            "required": ["task"],
        },
        run=run,
        parallel=True,
    )


async def _delegate(runtime: Runtime, target: str, task: str, args: dict[str, Any]) -> str:
    """Opens (or re-finds) the child conversation, runs it, and reports what came back."""
    parent_id = turn_conversation_id()
    parent = runtime.store.get(parent_id) if parent_id else None
    call_id = tool_call_id()
    child = runtime.store.for_parent_call(call_id) if call_id else None
    if child is None:
        if len(_children(runtime, parent)) >= MAX_DELEGATES:
            raise ToolError(texts.DELEGATE_TOO_MANY.format(limit=MAX_DELEGATES))
        child = _open_child(runtime, parent, target, task, args, call_id)
        runtime.scheduler.keep(asyncio.create_task(_run_child(runtime, child, task, target)))
    timeout = float(runtime.settings.approval_ttl_seconds) + WAIT_MARGIN_SECONDS
    run = await runtime.hub.wait_finished(child.id, timeout)
    if run is None:
        raise ToolError(texts.DELEGATE_TIMEOUT.format(conv_id=child.id))
    if parent is not None:
        # What the child spent is the parent's spend too, or a fan-out would cost the
        # parent's budget nothing and its cap would stop meaning anything.
        runtime.store.add_spend(parent.id, runtime.store.get(child.id).spent_usd)
    header = texts.DELEGATE_RESULT_HEADER.format(
        conv_id=child.id, status=run.status, spent=run.spent_usd or 0.0, steps=len(run.steps)
    )
    return f"{header}\n{_answer(runtime, child.id)}"


def _children(runtime: Runtime, parent: Conversation | None) -> list[Conversation]:
    """Everything this conversation has already delegated, found through the ids of its own
    tool calls — the store links a child to the call, not to the conversation."""
    if parent is None:
        return []
    calls = tuple(
        call.id
        for stored in runtime.store.history(parent.id)
        for call in stored.message.tool_calls
        if call.name == DELEGATE_TOOL_NAME
    )
    return runtime.store.children_of(calls)


async def _run_child(runtime: Runtime, child: Conversation, task: str, agent_id: str) -> None:
    """The child runs as its own tracked activity run, so it shows up in the UI on its own
    instead of disappearing inside the parent's single tool call."""
    deps = runtime.deps_for_child(agent_id)
    source = f"{DELEGATE}:{turn_conversation_id() or child.id}"
    events = run_turn(deps, child.id, task, source=source, depth=1)
    async for _ in tracked(runtime.hub, events, agent_id, source, child.title, child.id):
        pass


def _open_child(
    runtime: Runtime,
    parent: Conversation | None,
    target: str,
    task: str,
    args: dict[str, Any],
    call_id: str,
) -> Conversation:
    """The child inherits the parent's approval stance and what is left of its budget, so a
    fan-out cannot spend more than the parent was allowed in total."""
    cap = runtime.deps_for(target).settings.cost_cap_usd
    if parent is not None and parent.cost_cap_usd:
        remaining = max(parent.cost_cap_usd - parent.spent_usd, 0.0)
        cap = min(cap, remaining) if cap else remaining
    title = texts.DELEGATE_CONVERSATION_TITLE.format(agent=target, task=task[:TITLE_TASK_CHARS])
    child = runtime.store.create(
        title=title,
        autonomous=parent.autonomous if parent is not None else True,
        cost_cap_usd=cap,
        skills=tuple(str(s) for s in args.get("skills") or ()),
        agent_id=target,
        parent_call_id=call_id,
    )
    if parent is not None and parent.auto_approve:
        child = runtime.store.update(child.id, auto_approve=list(parent.auto_approve))
    return child


def _answer(runtime: Runtime, conv_id: str) -> str:
    """The child's last words. Everything before them is its own working-out, which the
    parent asked to be spared."""
    history = runtime.store.history(conv_id)
    replies = [m.message.content for m in history if m.message.role == "assistant"]
    last = replies[-1].strip() if replies else ""
    return last or texts.EMPTY_REPLY
