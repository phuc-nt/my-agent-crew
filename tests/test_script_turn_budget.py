"""The scripts of one turn share a count of the calls they may make: ten for each call of
the model the turn is allowed. The script that would pass it is ended there, what comes
after it is left unrun, and the turn stops (`agent/nested_calls.py`, `agent/loop.py`,
`agent/step_limit.py` over `script/tool.py`)."""

from __future__ import annotations

from textwrap import dedent

import pytest

from my_agent_crew import texts
from my_agent_crew import texts_script as t
from my_agent_crew.agent.events import DoneEvent, HaltedEvent, ToolResultEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.nested_calls import (
    NESTED_CALLS_PER_STEP,
    NestedBudget,
    nested_budget,
    start_nested_budget,
)
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.script.tool import SCRIPT_TOOL, script_tool
from my_agent_crew.tools import Tool
from my_agent_crew.turn_reply import collect_reply
from tests.conftest import collect

SCHEMA = {"type": "object", "properties": {}}
SPENT = t.SCRIPT_TURN_CALLS_SPENT.format(most=20)


def looping(times: int, call_id: str = "p1") -> ToolCall:
    source = f"for i in range({times}):\n    tools.row_read()\nprint('đọc xong {times}')"
    return ToolCall(call_id, SCRIPT_TOOL, {"script": source})


def scripted(source: str, call_id: str = "p1") -> ToolCall:
    return ToolCall(call_id, SCRIPT_TOOL, {"script": dedent(source)})


def a_turn(deps_factory, script, max_steps: int = 2):
    """Deps whose agent holds `row_read`, which only reads, `row_write`, which does not,
    and `tool_script`. Hands back the deps and what each of the two was asked."""
    read, written = [], []

    async def row_read(arguments: dict) -> str:
        read.append(arguments)
        return "một dòng"

    async def row_write(arguments: dict) -> str:
        written.append(arguments)
        return "đã ghi"

    tools = [
        Tool("row_read", "Đọc một dòng.", SCHEMA, row_read, replay_safe=True),
        Tool("row_write", "Ghi một dòng.", SCHEMA, row_write),
    ]
    deps = deps_factory(script=script, extra_tools=tools, max_steps=max_steps)
    deps.tools.register(script_tool(lambda: deps.tools, []))
    return deps, read, written


def results(events: list) -> list[ToolResultEvent]:
    return [event for event in events if isinstance(event, ToolResultEvent)]


def test_a_count_gives_all_that_was_asked_or_none_of_it_and_stays_spent():
    budget = NestedBudget(limit=5)

    assert budget.take(3) and budget.take(2) and (budget.used, budget.spent) == (5, False)
    assert budget.take(0) and not budget.spent
    assert not budget.take(1) and (budget.used, budget.spent) == (5, True)
    assert budget.take(0) and budget.spent  # what fits is still given; the turn ends anyway

    partly = NestedBudget(limit=5, used=3)
    assert not partly.take(3) and partly.used == 3  # none of a batch that does not fit whole


def test_a_turn_counts_ten_calls_for_each_call_of_the_model_from_nothing():
    first = start_nested_budget(12)
    first.take(7)

    assert (first.limit, NESTED_CALLS_PER_STEP) == (120, 10) and nested_budget() is first
    second = start_nested_budget(3)
    assert (second.limit, second.used, second.spent) == (30, 0, False)
    assert nested_budget() is second


async def test_the_script_that_passes_the_count_is_ended_there_and_the_turn_with_it(deps_factory):
    deps, read, _ = a_turn(
        deps_factory, [completion(tool_calls=[looping(21)]), completion("Xong.")]
    )
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đọc hết"))

    assert len(read) == 20  # the twenty-first was never made
    [result] = results(events)
    assert not result.ok and len(result.calls) == 20
    assert result.output == f"{t.SCRIPT_FAILED}\n{t.SCRIPT_HALTED.format(line=2, reason=SPENT)}"
    assert events[-1] == HaltedEvent(reason="nested_calls", spent_usd=pytest.approx(0.001))
    # The model is not asked again: one more refusal would not talk it out of scripting.
    assert len(deps.chain.providers["scripted"].requests) == 1


async def test_a_script_may_use_the_whole_count(deps_factory):
    deps, read, _ = a_turn(
        deps_factory, [completion(tool_calls=[looping(20)]), completion("Xong.")]
    )
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đọc hết"))

    assert len(read) == 20
    [result] = results(events)
    assert result.ok and result.output == "đọc xong 20"
    assert isinstance(events[-1], DoneEvent)


async def test_the_scripts_of_a_turn_share_one_count(deps_factory):
    script = [
        completion(tool_calls=[looping(20, "p1")]),
        completion(tool_calls=[looping(11, "p2")]),
        completion("Xong."),
    ]
    deps, read, _ = a_turn(deps_factory, script, max_steps=3)
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đọc hết"))

    assert len(read) == 30
    first, second = results(events)
    assert first.ok and not second.ok and len(second.calls) == 10
    assert t.SCRIPT_TURN_CALLS_SPENT.format(most=30) in second.output
    assert events[-1] == HaltedEvent(reason="nested_calls", spent_usd=pytest.approx(0.002))


async def test_what_was_asked_after_the_script_that_spent_the_count_is_closed_unrun(deps_factory):
    asked = [looping(21, "p1"), ToolCall("w1", "row_write", {}), looping(1, "p2")]
    deps, read, written = a_turn(deps_factory, [completion(tool_calls=asked), completion("Xong.")])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đọc rồi ghi"))

    assert len(read) == 20 and written == []
    spent, write, script = results(events)
    refusal = texts.NESTED_HALTED_TOOL.format(most=20)
    assert (write.tool_call_id, write.ok, write.output) == ("w1", False, refusal)
    assert (script.tool_call_id, script.ok, script.output) == ("p2", False, refusal)
    assert isinstance(events[-1], HaltedEvent) and events[-1].reason == "nested_calls"
    # Every call the model made has a result, so the conversation can carry on.
    history = [m.message for m in deps.store.history(conv.id)]
    assert [m.tool_call_id for m in history if m.role == "tool"] == ["p1", "w1", "p2"]


async def test_a_batch_that_does_not_fit_whole_is_not_made_in_part(deps_factory):
    source = """
        for i in range(15):
            tools.row_read()
        tools.batch([{"tool": "row_read"}] * 6)
        """
    deps, read, _ = a_turn(
        deps_factory, [completion(tool_calls=[scripted(source)]), completion("Xong.")]
    )
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đọc hết"))

    assert len(read) == 15
    [result] = results(events)
    assert not result.ok and len(result.calls) == 15
    assert result.output.endswith(t.SCRIPT_HALTED.format(line=4, reason=SPENT))
    assert events[-1].reason == "nested_calls"


async def test_a_script_cannot_catch_the_end_of_the_count(deps_factory):
    source = """
        for i in range(25):
            try:
                tools.row_read()
            except Exception:
                print("bắt được")
        print("chạy tiếp")
        """
    deps, read, _ = a_turn(
        deps_factory, [completion(tool_calls=[scripted(source)]), completion("Xong.")]
    )
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đọc hết"))

    assert len(read) == 20
    [result] = results(events)
    assert "bắt được" not in result.output and "chạy tiếp" not in result.output
    assert events[-1].reason == "nested_calls"


async def test_a_name_no_tool_answers_to_is_not_counted(deps_factory):
    source = """
        for i in range(5):
            try:
                tools.row_raed()
            except Exception:
                pass
        for i in range(20):
            tools.row_read()
        print("đọc xong")
        """
    deps, read, _ = a_turn(
        deps_factory, [completion(tool_calls=[scripted(source)]), completion("Xong.")]
    )
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đọc hết"))

    assert len(read) == 20
    [result] = results(events)
    assert result.ok and result.output == "đọc xong"
    assert isinstance(events[-1], DoneEvent)


async def test_the_next_turn_counts_from_nothing(deps_factory):
    script = [
        completion(tool_calls=[looping(20, "p1")]),
        completion("Xong."),
        completion(tool_calls=[looping(20, "p2")]),
        completion("Xong nữa."),
    ]
    deps, read, _ = a_turn(deps_factory, script)
    conv = deps.store.create()

    await collect(run_turn(deps, conv.id, "đọc hết"))
    events = await collect(run_turn(deps, conv.id, "đọc lần nữa"))

    assert len(read) == 40
    assert results(events)[-1].ok and isinstance(events[-1], DoneEvent)


async def test_a_turn_ended_on_the_count_reads_as_words_where_a_person_reads_it(deps_factory):
    deps, _, _ = a_turn(deps_factory, [completion(tool_calls=[looping(21)])])
    conv = deps.store.create()

    reply = await collect_reply(run_turn(deps, conv.id, "đọc hết"))

    words = texts.HALT_REASONS["nested_calls"]
    assert reply.status == "halted"
    assert texts.REPLY_HALTED.format(reason=words, spent=0.001) in reply.text
    assert "(nested_calls)" not in reply.text
