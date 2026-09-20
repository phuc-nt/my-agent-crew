"""Handing a task to another agent: what comes back, what it costs, and the limits that
keep one delegation from turning into a fan-out nobody asked for."""

from __future__ import annotations

from dataclasses import replace

import pytest

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.agent.turn_context import set_tool_call_id, set_turn_conversation
from my_agent_crew.agents.profile import WORK
from my_agent_crew.config import Route
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store import Store
from my_agent_crew.tools.delegate import DELEGATE_TOOL_NAME, MAX_DELEGATES
from my_agent_crew.tools.registry import ToolRegistry
from tests.conftest import collect


def agent(deps: AgentDeps, agent_id: str, *, mode: str = WORK, delegates: tuple[str, ...] = ()):
    profile = replace(deps.profile, id=agent_id, name=agent_id, mode=mode, delegates=delegates)
    # A fresh registry per agent: they would otherwise share one object and the second
    # `register` would collide with the first agent's delegate tool.
    tools = ToolRegistry([deps.tools.get(n) for n in deps.tools.names()])
    return replace(deps, profile=profile, tools=tools)


@pytest.fixture
def runtime(deps_factory, store: Store) -> Runtime:
    """A boss that may delegate to `worker`, both answering through the echo provider."""
    base = deps_factory(routes=(Route("fake", "echo"),))
    agents = {
        "boss": agent(base, "boss", delegates=("worker",)),
        "worker": agent(base, "worker"),
    }
    rt = Runtime(base.settings, store, agents, ActivityHub(store))
    rt.wire_delegation()
    return rt


async def delegate(runtime: Runtime, parent_id: str, call_id: str, **args) -> str:
    """Calls the tool the way the loop would: inside a turn, with a call id in context."""
    set_turn_conversation(parent_id, 0)
    set_tool_call_id(call_id)
    result = await runtime.deps_for("boss").tools.execute(DELEGATE_TOOL_NAME, args)
    return result.output


async def test_the_parent_gets_the_child_answer_and_pays_for_it(runtime: Runtime):
    parent = runtime.store.create(agent_id="boss", autonomous=True)
    out = await delegate(runtime, parent.id, "call-1", task="đếm số tệp", agent="worker")

    child = runtime.store.for_parent_call("call-1")
    assert child is not None and child.agent_id == "worker"
    assert "đếm số tệp" in out  # the echo provider replies with the task it was given
    assert f"conversation={child.id}" in out
    assert runtime.store.get(parent.id).spent_usd == runtime.store.get(child.id).spent_usd


async def test_the_child_conversation_is_separate_from_the_parent(runtime: Runtime):
    parent = runtime.store.create(agent_id="boss", autonomous=True)
    runtime.store.append(parent.id, _user("chuyện riêng của cha"))
    await delegate(runtime, parent.id, "call-1", task="việc con", agent="worker")

    child = runtime.store.for_parent_call("call-1")
    text = " ".join(m.message.content for m in runtime.store.history(child.id))
    assert "chuyện riêng của cha" not in text


async def test_delegating_to_an_agent_outside_the_list_is_refused(runtime: Runtime):
    parent = runtime.store.create(agent_id="boss", autonomous=True)
    out = await delegate(runtime, parent.id, "call-1", task="việc", agent="stranger")

    assert "stranger" in out and "worker" in out
    assert runtime.store.for_parent_call("call-1") is None


async def test_an_agent_may_always_delegate_to_itself(runtime: Runtime):
    parent = runtime.store.create(agent_id="boss", autonomous=True)
    await delegate(runtime, parent.id, "call-1", task="tự làm lại")

    child = runtime.store.for_parent_call("call-1")
    assert child is not None and child.agent_id == "boss"


async def test_a_child_agent_does_not_get_the_delegate_tool(runtime: Runtime):
    assert runtime.deps_for("boss").tools.get(DELEGATE_TOOL_NAME) is not None
    assert runtime.deps_for_child("boss").tools.get(DELEGATE_TOOL_NAME) is None


async def test_a_delegated_turn_refuses_to_delegate_again(runtime: Runtime):
    """The second guard: even holding the tool, a turn one level down will not use it."""
    parent = runtime.store.create(agent_id="boss", autonomous=True)
    set_turn_conversation(parent.id, 1)
    set_tool_call_id("call-1")
    out = await runtime.deps_for("boss").tools.execute(DELEGATE_TOOL_NAME, {"task": "việc"})

    assert "không được giao việc tiếp" in out.output.lower()
    assert runtime.store.for_parent_call("call-1") is None


async def test_resuming_the_same_call_reuses_the_child_it_already_opened(runtime: Runtime):
    """What an interrupted turn does on the way back: the same tool call must not open a
    second conversation and pay for the work twice."""
    parent = runtime.store.create(agent_id="boss", autonomous=True)
    first = await delegate(runtime, parent.id, "call-1", task="việc", agent="worker")
    child = runtime.store.for_parent_call("call-1")
    turns_before = len(runtime.store.history(child.id))

    again = await delegate(runtime, parent.id, "call-1", task="việc", agent="worker")

    assert [c.id for c in runtime.store.children_of(("call-1",))] == [child.id]
    # The same answer, read back off the child that already ran rather than run afresh.
    assert again == first
    assert len(runtime.store.history(child.id)) == turns_before


async def test_one_conversation_may_only_delegate_so_many_times(runtime: Runtime):
    parent = runtime.store.create(agent_id="boss", autonomous=True)
    calls = []
    for i in range(MAX_DELEGATES):
        call_id = f"call-{i}"
        calls.append(call_id)
        runtime.store.append(parent.id, _assistant_call(call_id))
        await delegate(runtime, parent.id, call_id, task=f"việc {i}", agent="worker")
    assert len(runtime.store.children_of(tuple(calls))) == MAX_DELEGATES

    runtime.store.append(parent.id, _assistant_call("call-over"))
    out = await delegate(runtime, parent.id, "call-over", task="một việc nữa", agent="worker")

    assert str(MAX_DELEGATES) in out
    assert runtime.store.for_parent_call("call-over") is None


async def test_the_child_inherits_what_is_left_of_the_parent_budget(runtime: Runtime):
    parent = runtime.store.create(agent_id="boss", autonomous=True, cost_cap_usd=1.0)
    runtime.store.add_spend(parent.id, 0.75)
    await delegate(runtime, parent.id, "call-1", task="việc", agent="worker")

    child = runtime.store.for_parent_call("call-1")
    assert child.cost_cap_usd == pytest.approx(0.25)


async def test_a_work_agent_can_reach_its_peer_through_a_whole_turn(runtime: Runtime):
    """End to end through the loop rather than the tool alone, so the call id the guard
    relies on is the one `settle_tool_calls` actually sets."""
    parent = runtime.store.create(agent_id="boss", autonomous=True)
    deps = runtime.deps_for("boss")
    events = run_turn(deps, parent.id, f'/tool {DELEGATE_TOOL_NAME} {{"task": "khảo sát"}}')
    await collect(events)

    children = runtime.store.list("boss")
    assert any(c.parent_call_id for c in children)


def _user(text: str) -> Message:
    return Message(role="user", content=text)


def _assistant_call(call_id: str) -> Message:
    """An assistant message asking for a delegation, which is how the store learns that a
    call id belongs to this conversation."""
    return Message(
        role="assistant",
        tool_calls=(ToolCall(id=call_id, name=DELEGATE_TOOL_NAME, arguments={}),),
    )
