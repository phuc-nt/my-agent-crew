"""How `tool_output_read` reaches an agent: only agents that may call it get a spill file and
a pointer to it, the prompt's stubs name the id only for them, and a whole turn round-trips."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

import pytest

from my_agent_crew.agent.events import ToolResultEvent
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.agent.prompt import turn_messages
from my_agent_crew.agent.turn_context import set_tool_call_id, set_turn_conversation
from my_agent_crew.config import Settings
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.server.tool_assembly import build_tools
from my_agent_crew.tools import Tool, ToolRegistry
from my_agent_crew.tools.output_read import build_output_read_tool
from my_agent_crew.tools.output_spill import Spill
from tests.conftest import collect


@pytest.fixture(autouse=True)
def no_leftover_context() -> Iterator[None]:
    yield
    set_turn_conversation("", 0)
    set_tool_call_id("")


def _assemble(settings: Settings, store, tools: tuple[str, ...]) -> ToolRegistry:
    import httpx

    from my_agent_crew.agents import default_profile

    profile = replace(default_profile(settings), tools=tools)
    return build_tools(profile, httpx.AsyncClient(), store, [])


def test_an_agent_with_no_allow_list_can_read_back_and_spills(settings: Settings, store):
    registry = _assemble(settings, store, ())

    assert registry.get("tool_output_read") is not None
    assert registry.spill is not None


def test_an_allow_list_with_the_tool_spills_and_one_without_it_does_not(settings: Settings, store):
    with_it = _assemble(settings, store, ("workspace_read", "tool_output_read"))
    without = _assemble(settings, store, ("workspace_read",))

    assert with_it.spill is not None and with_it.names() == ["workspace_read", "tool_output_read"]
    assert without.spill is None and without.get("tool_output_read") is None


def _stubbable(count: int) -> list:
    return [
        Message(role="tool", content="x" * 500, tool_call_id=f"call-{i}", name="workspace_read")
        for i in range(count)
    ]


def test_the_prompt_stubs_name_the_id_only_when_the_agent_has_the_tool(deps_factory, store):
    from types import SimpleNamespace

    deps = deps_factory()
    conv = store.create()
    history = [SimpleNamespace(message=m) for m in _stubbable(21)]
    reading = replace(
        deps, tools=ToolRegistry([build_output_read_tool(store, Spill(deps.settings.home), 4000)])
    )

    plain = turn_messages(deps, conv, history)[1].content
    rereadable = turn_messages(reading, conv, history)[1].content

    assert "tool_output_read" not in plain
    assert "tool_output_read id=call-0" in rereadable


async def test_a_long_result_is_read_back_through_the_loop(deps_factory, store):
    big = "".join(f"line {i:05d}\n" for i in range(2000))  # 22,000 characters

    async def produce(_args) -> str:
        return big

    producer = Tool(name="produce", description="d", parameters={"type": "object"}, run=produce)
    deps = deps_factory(tool_output_chars=3000)
    spill = Spill(deps.settings.home)
    reader = build_output_read_tool(store, spill, 3000)
    registry = ToolRegistry([producer, reader], 3000, spill=spill)
    deps = AgentDeps(
        settings=deps.settings, chain=_chain(deps, big), tools=registry, store=store,
        skills=deps.skills, profile=deps.profile,
    )  # fmt: skip
    conv = store.create()

    events = await collect(run_turn(deps, conv.id, "go"))

    results = [e for e in events if isinstance(e, ToolResultEvent)]
    assert len(results) == 2 and all(r.ok for r in results)
    first, second = results[0].output, results[1].output
    assert len(first) <= 3000 and "tool_output_read id=c1" in first
    header = second.split("\n")[0]
    assert header.startswith("[bản gốc chưa rút gọn, 10000-") and f"/{len(big)} ký tự]" in header
    assert big[10000:10100] in second and big[10000:10100] not in first


def _chain(deps: AgentDeps, big: str):
    from my_agent_crew.llm.fake import ScriptedProvider
    from my_agent_crew.llm.provider import ProviderChain

    script = [
        completion(tool_calls=(ToolCall("c1", "produce", {}),)),
        completion(tool_calls=(ToolCall("c2", "tool_output_read", {"id": "c1", "offset": 10000}),)),
        completion("xong"),
    ]
    return ProviderChain({"scripted": ScriptedProvider(script)}, deps.settings.routes)
