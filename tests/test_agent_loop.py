"""The turn loop: streaming, tool execution, budget, step limit, provider failure."""

import pytest

from my_agent_crew.agent.events import (
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    HaltedEvent,
    RouteFallbackEvent,
    TextDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
    to_dict,
)
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.turn_context import CHAT, JOB, set_turn_source, turn_source
from my_agent_crew.config import Route
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.tools import Tool
from tests.conftest import collect


async def test_plain_reply_streams_then_persists(deps_factory):
    deps = deps_factory(script=[completion("Xin chào bạn")])
    conv = deps.store.create()
    events = await collect(run_turn(deps, conv.id, "chào"))
    text = "".join(e.text for e in events if isinstance(e, TextDeltaEvent))
    assert text == "Xin chào bạn"
    assert isinstance(events[-2], AssistantMessageEvent)
    assert isinstance(events[-1], DoneEvent)
    roles = [m.message.role for m in deps.store.history(conv.id)]
    assert roles == ["user", "assistant"]


async def test_tool_call_executes_and_feeds_result_back(deps_factory):
    deps = deps_factory(
        script=[
            completion(tool_calls=(ToolCall("c1", "workspace_list", {"path": "."}),)),
            completion("Thư mục trống."),
        ]
    )
    conv = deps.store.create()
    events = await collect(run_turn(deps, conv.id, "liệt kê"))
    kinds = [to_dict(e)["type"] for e in events if not isinstance(e, TextDeltaEvent)]
    assert kinds == ["assistant_message", "tool_call", "tool_result", "assistant_message", "done"]
    result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert result.ok
    second_request = deps.chain.providers["scripted"].requests[1]
    tool_msgs = [m for m in second_request.messages if m.role == "tool"]
    assert tool_msgs[0].tool_call_id == "c1"
    roles = [m.message.role for m in deps.store.history(conv.id)]
    assert roles == ["user", "assistant", "tool", "assistant"]


async def test_system_prompt_is_first_and_includes_skill(deps_factory):
    deps = deps_factory(script=[completion("ok")])
    conv = deps.store.create()
    await collect(run_turn(deps, conv.id, "hi"))
    request = deps.chain.providers["scripted"].requests[0]
    assert request.messages[0].role == "system"
    assert "cite-sources" in request.messages[0].content
    assert "workspace_list" in {t.name for t in request.tools}


async def test_budget_halts_before_next_model_call(deps_factory):
    deps = deps_factory(
        script=[
            completion(tool_calls=(ToolCall("c1", "workspace_list", {}),), cost_usd=0.02),
            completion("never"),
        ]
    )
    conv = deps.store.create(cost_cap_usd=0.01)
    events = await collect(run_turn(deps, conv.id, "go"))
    assert isinstance(events[-1], HaltedEvent) and events[-1].reason == "budget"
    assert any(isinstance(e, ToolResultEvent) for e in events)
    assert len(deps.chain.providers["scripted"].requests) == 1


async def test_unknown_cost_is_counted_not_treated_as_free(deps_factory):
    deps = deps_factory(script=[completion("ok", cost_usd=None)])
    conv = deps.store.create()
    events = await collect(run_turn(deps, conv.id, "hi"))
    assert events[-1] == DoneEvent(spent_usd=0.0, unknown_cost_calls=1)


async def test_max_steps_halts_a_tool_loop(deps_factory):
    calls = [completion(tool_calls=(ToolCall(f"c{i}", "workspace_list", {}),)) for i in range(10)]
    deps = deps_factory(script=calls, max_steps=3)
    conv = deps.store.create()
    events = await collect(run_turn(deps, conv.id, "loop"))
    assert isinstance(events[-1], HaltedEvent) and events[-1].reason == "max_steps"
    assert len(deps.chain.providers["scripted"].requests) == 3


async def test_provider_failure_becomes_error_event_and_keeps_user_message(deps_factory):
    deps = deps_factory(script=[ProviderError("all down")])
    conv = deps.store.create()
    events = await collect(run_turn(deps, conv.id, "hi"))
    assert isinstance(events[-1], ErrorEvent) and "all down" in events[-1].message
    assert [m.message.role for m in deps.store.history(conv.id)] == ["user"]


async def test_route_fallback_is_an_event_before_the_next_route_answers(deps_factory):
    routes = (Route("scripted", "m"), Route("scripted", "m2"))
    deps = deps_factory(script=[ProviderError("m busy"), completion("ok")], routes=routes)
    conv = deps.store.create()
    events = await collect(run_turn(deps, conv.id, "hi"))
    assert events[0] == RouteFallbackEvent(provider="scripted", model="m", error="m busy")
    assert isinstance(events[-1], DoneEvent)
    assert to_dict(events[0])["type"] == "route_fallback"


async def test_unknown_tool_name_returns_error_to_model(deps_factory):
    deps = deps_factory(
        script=[completion(tool_calls=(ToolCall("c1", "nope", {}),)), completion("sorry")]
    )
    conv = deps.store.create()
    events = await collect(run_turn(deps, conv.id, "x"))
    result = next(e for e in events if isinstance(e, ToolResultEvent))
    assert result.ok is False and "nope" in result.output


async def test_events_serialise_with_type_tag():
    assert to_dict(ToolCallEvent("c", "t", {"a": 1})) == {
        "type": "tool_call",
        "tool_call_id": "c",
        "name": "t",
        "arguments": {"a": 1},
    }


async def test_echo_route_works_end_to_end_without_keys(deps_factory):
    from my_agent_crew.config import Route

    deps = deps_factory(routes=(Route("fake", "echo"),))
    conv = deps.store.create()
    events = await collect(run_turn(deps, conv.id, "/tool workspace_list"))
    assert any(isinstance(e, ToolResultEvent) and e.ok for e in events)
    assert isinstance(events[-1], DoneEvent)


@pytest.mark.parametrize("text", ["/tool nope", "/tool workspace_list {bad"])
async def test_echo_route_explains_bad_directives(deps_factory, text):
    from my_agent_crew.config import Route

    deps = deps_factory(routes=(Route("fake", "echo"),))
    conv = deps.store.create()
    events = await collect(run_turn(deps, conv.id, text))
    reply = next(e for e in events if isinstance(e, AssistantMessageEvent))
    assert reply.tool_calls == [] and reply.content


async def test_the_turn_records_where_the_work_came_from(deps_factory):
    """Tools that write memory ask who is at the other end, so the source must reach them."""
    seen: list[str] = []

    async def spy(args):
        seen.append(turn_source())
        return "ok"

    tool = Tool(name="spy", description="", parameters={"type": "object"}, run=spy)
    deps = deps_factory(
        script=[completion(tool_calls=(ToolCall("c1", "spy", {}),)), completion("xong")],
        extra_tools=[tool],
    )
    conv = deps.store.create()
    set_turn_source(CHAT)
    await collect(run_turn(deps, conv.id, "chạy", source="job:coach/brief"))
    assert seen == [JOB]


async def test_a_chat_turn_is_the_default_source(deps_factory):
    seen: list[str] = []

    async def spy(args):
        seen.append(turn_source())
        return "ok"

    tool = Tool(name="spy", description="", parameters={"type": "object"}, run=spy)
    deps = deps_factory(
        script=[completion(tool_calls=(ToolCall("c1", "spy", {}),)), completion("xong")],
        extra_tools=[tool],
    )
    conv = deps.store.create()
    set_turn_source(JOB)
    await collect(run_turn(deps, conv.id, "chạy"))
    assert seen == [CHAT]


async def test_a_blank_reply_is_retried_rather_than_passed_off_as_a_finished_turn(deps_factory):
    deps = deps_factory(script=[completion(""), completion("Xin lỗi, đây là câu trả lời.")])
    conv = deps.store.create()
    events = await collect(run_turn(deps, conv.id, "chào"))
    assert isinstance(events[-1], DoneEvent)
    assert events[-2].content == "Xin lỗi, đây là câu trả lời."
    # The silence is not replayed to the model: continuing from its own blank
    # tends to produce another blank.
    retry = deps.chain.providers["scripted"].requests[1]
    assert [m.role for m in retry.messages] == ["system", "user"]


async def test_two_blank_replies_in_a_row_name_the_model_instead_of_going_quiet(deps_factory):
    deps = deps_factory(script=[completion(""), completion("   ")])
    conv = deps.store.create()
    events = await collect(run_turn(deps, conv.id, "chào"))
    assert isinstance(events[-1], ErrorEvent)
    assert "scripted" in events[-1].message
    assert len(deps.chain.providers["scripted"].requests) == 2
