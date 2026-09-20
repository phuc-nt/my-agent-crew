"""Which tool calls in one message run together, and which wait their turn."""

from __future__ import annotations

import asyncio

import pytest

from my_agent_crew.agent.events import ToolResultEvent
from my_agent_crew.agent.tool_batches import MAX_PARALLEL_CALLS, split_batches
from my_agent_crew.agent.tool_calls import settle_tool_calls
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.tools import Tool, ToolRegistry
from tests.conftest import collect


def call(name: str, call_id: str = "") -> ToolCall:
    return ToolCall(id=call_id or f"{name}-1", name=name, arguments={})


def tool(name: str, *, parallel: bool = False, requires_approval: bool = False) -> Tool:
    async def run(args: dict) -> str:
        return name

    return Tool(
        name=name,
        description=name,
        parameters={"type": "object", "properties": {}},
        run=run,
        parallel=parallel,
        requires_approval=requires_approval,
    )


@pytest.fixture
def tools() -> ToolRegistry:
    return ToolRegistry([tool("wait", parallel=True), tool("touch"), tool("wait2", parallel=True)])


def shapes(batches: list[list[ToolCall]]) -> list[list[str]]:
    return [[c.name for c in b] for b in batches]


def test_calls_that_wait_are_grouped_together(tools: ToolRegistry):
    calls = [call("wait", "a"), call("wait2", "b")]
    assert shapes(split_batches(calls, tools, lambda c: True)) == [["wait", "wait2"]]


def test_a_tool_that_touches_the_workspace_stays_on_its_own(tools: ToolRegistry):
    calls = [call("wait", "a"), call("touch", "b"), call("wait2", "c")]
    assert shapes(split_batches(calls, tools, lambda c: True)) == [["wait"], ["touch"], ["wait2"]]


def test_a_call_awaiting_a_decision_is_never_batched(tools: ToolRegistry):
    """It stops the turn, so it has to be the only thing being settled."""
    calls = [call("wait", "a"), call("wait2", "b")]
    batches = split_batches(calls, tools, lambda c: c.id != "b")
    assert shapes(batches) == [["wait"], ["wait2"]]


def test_an_unknown_tool_is_left_sequential(tools: ToolRegistry):
    calls = [call("wait", "a"), call("nobody", "b")]
    assert shapes(split_batches(calls, tools, lambda c: True)) == [["wait"], ["nobody"]]


def test_one_message_cannot_fan_out_without_limit(tools: ToolRegistry):
    calls = [call("wait", str(i)) for i in range(MAX_PARALLEL_CALLS + 2)]
    batches = split_batches(calls, tools, lambda c: True)
    assert [len(b) for b in batches] == [MAX_PARALLEL_CALLS, 2]


async def test_batched_calls_run_at_the_same_time(deps_factory, store):
    """Two slow tools in one message take about as long as one, and their results are
    written back in the order the model asked for, not the order they finished."""
    order: list[str] = []

    def slow(name: str, delay: float) -> Tool:
        async def run(args: dict) -> str:
            await asyncio.sleep(delay)
            order.append(name)
            return name

        return Tool(
            name=name,
            description=name,
            parameters={"type": "object", "properties": {}},
            run=run,
            parallel=True,
        )

    deps = deps_factory(extra_tools=[slow("slow", 0.05), slow("quick", 0.01)])
    conv = store.create(autonomous=True)
    store.append(
        conv.id,
        Message(role="assistant", tool_calls=(call("slow", "a"), call("quick", "b"))),
    )

    started = asyncio.get_running_loop().time()
    events = await collect(settle_tool_calls(deps, conv.id))
    elapsed = asyncio.get_running_loop().time() - started

    assert order == ["quick", "slow"]  # they really did overlap
    assert elapsed < 0.05 + 0.01  # sequential would have cost the sum
    results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert [e.name for e in results] == ["slow", "quick"]


async def test_a_tool_that_is_not_parallel_still_runs_one_at_a_time(deps_factory, store):
    order: list[str] = []

    def step(name: str, delay: float) -> Tool:
        async def run(args: dict) -> str:
            await asyncio.sleep(delay)
            order.append(name)
            return name

        return Tool(
            name=name,
            description=name,
            parameters={"type": "object", "properties": {}},
            run=run,
        )

    deps = deps_factory(extra_tools=[step("first", 0.03), step("second", 0.001)])
    conv = store.create(autonomous=True)
    store.append(
        conv.id,
        Message(role="assistant", tool_calls=(call("first", "a"), call("second", "b"))),
    )

    await collect(settle_tool_calls(deps, conv.id))

    assert order == ["first", "second"]
