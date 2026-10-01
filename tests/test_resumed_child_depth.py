"""A delegated child stays a child when its turn is picked up again: after an approval,
a question or a restart, the turn starts without the depth the delegation gave it, and
the conversation itself has to say it is one level down."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.events import ToolResultEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.turn_context import turn_depth
from my_agent_crew.agents.profile import WORK
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.tools.registry import Tool, ToolRegistry, ToolResult
from tests.conftest import collect


def _depth_probe(seen: list[int]) -> Tool:
    async def run(args: dict[str, Any]) -> ToolResult:
        seen.append(turn_depth())
        return ToolResult(ok=True, output="ok")

    return Tool(name="depth_probe", description="", parameters={"type": "object"}, run=run)


async def _depth_inside(deps_factory, parent_call_id: str, **depth: int) -> int:
    seen: list[int] = []
    script = [completion(tool_calls=(ToolCall("c1", "depth_probe", {}),)), completion("xong")]
    deps = deps_factory(script=script, extra_tools=[_depth_probe(seen)])
    conv = deps.store.create(parent_call_id=parent_call_id, autonomous=True)
    await collect(run_turn(deps, conv.id, "việc", **depth))
    return seen[0]


async def test_a_child_resumed_without_a_depth_still_runs_one_level_down(deps_factory):
    assert await _depth_inside(deps_factory, "call-1") == 1


async def test_a_conversation_the_person_started_keeps_depth_zero(deps_factory):
    assert await _depth_inside(deps_factory, "") == 0


async def test_a_delegated_child_keeps_the_depth_it_was_given(deps_factory):
    assert await _depth_inside(deps_factory, "call-1", depth=1) == 1


async def test_a_resumed_child_with_the_delegate_tool_cannot_hand_work_on(deps_factory, store):
    """Resuming goes through `deps_for_conversation`, which hands back the agent with its
    delegate tool: only the depth stops a child from fanning out further."""
    call = ToolCall("d1", "delegate", {"task": "đếm tệp", "agent": "worker"})
    base = deps_factory(script=[completion(tool_calls=(call,)), completion("xong")])
    tools = ToolRegistry([base.tools.get(n) for n in base.tools.names()])
    boss = replace(base, profile=replace(base.profile, id="boss", mode=WORK, delegates=("worker",)))
    worker = replace(base, profile=replace(base.profile, id="worker", mode=WORK), tools=tools)
    runtime = Runtime(base.settings, store, {"boss": boss, "worker": worker}, ActivityHub(store))
    runtime.wire_delegation()
    child = store.create(agent_id="boss", parent_call_id="call-1", autonomous=True)
    store.append(child.id, Message(role="user", content="việc được giao"))

    events = await collect(run_turn(runtime.deps_for_conversation(child.id), child.id, None))

    result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert not result.ok and texts.DELEGATE_TOO_DEEP in result.output
    assert store.for_parent_call("d1") is None
