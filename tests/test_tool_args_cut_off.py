"""Broken tool calls told apart: a call cut off by the model's output limit is answered
with "split it", not "send it again", and calls broken in different ways are not taken
for a loop, while the same broken call sent over and over still is."""

from __future__ import annotations

from typing import Any

from my_agent_crew import texts
from my_agent_crew.agent.events import AssistantMessageEvent, DoneEvent, ToolResultEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.loop_guard import OK, REDIRECT, LoopGuard
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.tool_call_buffer import CUT_OFF, ToolCallBuffer
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.tools.registry import Tool, ToolError, ToolRegistry
from tests.conftest import collect
from tests.test_openrouter import delta, provider_with, sse

WHOLE = '{"path": "a.md"}'
BROKEN = '{"title": "Kế hoạch", "content": "dòng một\\ndòng hai'


def _buffer(*raws: str) -> ToolCallBuffer:
    buffer = ToolCallBuffer()
    for index, raw in enumerate(raws):
        fn = {"name": f"t{index}", "arguments": raw}
        buffer.feed([{"index": index, "id": f"c{index}", "function": fn}])
    return buffer


def test_only_the_call_still_being_written_when_output_ran_out_is_marked_cut_off():
    first, last = _buffer('{"a": ', BROKEN).calls(cut_off=True)
    assert first.invalid and not first.invalid.startswith(CUT_OFF)
    assert last.invalid.startswith(CUT_OFF)
    assert last.invalid.removeprefix(CUT_OFF) == _buffer(BROKEN).calls()[0].invalid


def test_a_last_call_that_parsed_or_a_reply_that_ended_normally_is_not_marked():
    assert _buffer(BROKEN, WHOLE).calls(cut_off=True)[1].invalid == ""
    assert not _buffer(BROKEN).calls()[0].invalid.startswith(CUT_OFF)


async def test_a_stream_that_stops_at_the_length_limit_marks_its_last_call():
    head = {"index": 0, "id": "c1", "function": {"name": "artifact_create", "arguments": BROKEN}}
    body = sse(delta(tool_calls=[head]), delta(finish="length"))
    items = await collect(provider_with(body).stream([Message(role="user", content="hi")], [], "m"))
    [call] = items[-1].message.tool_calls
    assert call.invalid.startswith(CUT_OFF) and items[-1].finish_reason == "length"


async def test_a_cut_off_call_is_told_to_split_rather_than_resend(deps_factory):
    cut = ToolCall("c1", "workspace_list", {}, invalid=CUT_OFF + "51 chars; cut off at char 51")
    deps = deps_factory(script=[completion(tool_calls=(cut,)), completion("xong")])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "viết tài liệu"))

    [result] = [e for e in events if isinstance(e, ToolResultEvent)]
    expected = texts.TOOL_ARGS_CUT_OFF.format(name="workspace_list", detail=cut.invalid)
    assert not result.ok and result.output == expected
    assert "Hãy gửi lại lời gọi này" not in result.output


async def test_the_assistant_event_carries_what_broke_each_call(deps_factory):
    broken = ToolCall("c1", "workspace_list", {}, invalid="3 chars; cut off at char 3")
    deps = deps_factory(script=[completion(tool_calls=(broken,)), completion("xong")])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "liệt kê"))

    first = next(e for e in events if isinstance(e, AssistantMessageEvent))
    assert first.tool_calls == [broken.to_dict()]
    assert first.tool_calls[0]["invalid"] == broken.invalid


def _broken(detail: str) -> dict[str, Any]:
    return ToolCall("c", "artifact_create", {}, invalid=detail).to_dict()


def test_calls_broken_in_different_places_are_not_a_repeat():
    guard = LoopGuard()
    verdicts = [guard.observe([_broken(f"{n} chars; cut off at char {n}")]) for n in range(6)]
    assert verdicts == [OK] * 6


def test_the_same_broken_call_sent_three_times_is_still_a_repeat():
    guard = LoopGuard()
    verdicts = [guard.observe([_broken("9 chars; cut off at char 9")]) for _ in range(3)]
    assert verdicts == [OK, OK, REDIRECT]


async def test_six_differently_broken_calls_in_a_row_neither_redirect_nor_halt(deps_factory):
    script = [
        *(
            completion(tool_calls=(ToolCall(f"c{n}", "workspace_list", {}, invalid=f"{n} chars"),))
            for n in range(6)
        ),
        completion("xong"),
    ]
    deps = deps_factory(script=script)
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "liệt kê"))

    assert isinstance(events[-1], DoneEvent)
    notes = [m.message.content for m in deps.store.history(conv.id) if m.message.role == "user"]
    assert notes == ["liệt kê"]


async def test_a_tool_error_longer_than_the_cap_is_cut_like_any_output():
    async def run(args: dict[str, Any]) -> str:
        raise ToolError("x" * 300_000)

    registry = ToolRegistry([Tool("loud", "", {"type": "object"}, run)], limit=8000)
    result = await registry.execute("loud", {})
    assert not result.ok and len(result.output) <= 8000
    assert result.output.startswith(texts.TOOL_FAILED.format(error="xxx"))
