"""Each call a script makes is told the moment it ends, while the script still runs: the
turn sends it, the run lists and bills it and the conversation is charged it at once, and
the script's result neither lists nor charges it a second time (`agent/tool_run.py`,
`agent/nested_calls.py` and `activity/tool_steps.py` over `script/tool.py`)."""

from __future__ import annotations

import asyncio
from textwrap import dedent
from types import SimpleNamespace
from typing import Any

import pytest

from my_agent_crew.activity.steps import apply_event
from my_agent_crew.agent.events import NestedCallEvent, ToolCallEvent, ToolResultEvent, to_dict
from my_agent_crew.agent.nested_calls import note_nested_call
from my_agent_crew.agent.tool_run import CallRun, charge_nested, not_yet_told
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.script.tool import SCRIPT_TOOL
from my_agent_crew.store import Store
from my_agent_crew.store.runs import RUNNING, RunRecord
from my_agent_crew.tools import Tool, ToolRegistry, ToolResult
from my_agent_crew.tools.result import NestedCall
from tests.queue_helpers import until
from tests.restart_helpers import stored_run
from tests.test_mcp_turns import say
from tests.test_script_turns import RUN, reading, running, scripting, the_result, the_step

PAID = {"name": "paid_read", "ok": True, "cost_usd": 0.004, "metered": True}
OTHER = {"name": "paid_read", "ok": False, "cost_usd": 0.002, "metered": True}
UNPRICED = {"name": "unpriced_read", "ok": True, "cost_usd": None, "metered": True}
FREE = {"name": "free_read", "ok": True, "cost_usd": 0.5, "metered": False}


def a_run() -> RunRecord:
    run = RunRecord("r1", "default", "c1", "chat", "t", RUNNING, "2026-10-06T08:00:00")
    apply_event(run, ToolCallEvent("p1", SCRIPT_TOOL, {"script": "…"}), 10.0)
    return run


def waiting(name: str, gate: asyncio.Event, **paid: Any) -> Tool:
    """A tool that only reads, and answers once `gate` is opened."""

    async def run(arguments: dict[str, Any]) -> ToolResult:
        await gate.wait()
        return ToolResult(ok=True, output=name, **paid)

    return Tool(name, f"Đọc {name}.", {"type": "object", "properties": {}}, run, replay_safe=True)


def listed(app) -> list[dict[str, Any]]:
    """The calls on the script's step so far; none while the run or the step is not there."""
    run = app.runtime.store.runs.latest_for_conversation(app.conv.id)
    steps = [step for step in (run.steps if run else []) if step.get("name") == SCRIPT_TOOL]
    return steps[0].get("calls", []) if steps else []


async def test_the_turn_sends_each_call_of_a_script_between_its_call_and_its_result(served):
    app, _ = await scripting(served, [completion(tool_calls=[RUN]), completion("Xong.")])

    events = await say(app)

    kinds = [event["type"] for event in events]
    at = kinds.index("tool_call")
    assert kinds[at : at + 4] == ["tool_call", "nested_call", "nested_call", "tool_result"]
    first, second = events[at + 1], events[at + 2]
    assert (first["tool_call_id"], first["index"]) == ("p1", 0)
    assert (second["tool_call_id"], second["index"]) == ("p1", 1)
    # What was sent one by one is what the result lists, and what the run keeps.
    result = the_result(events)
    assert [first["call"], second["call"]] == result["calls"] == the_step(app)["calls"]
    assert [call["arguments"] for call in result["calls"]] == [
        {"query": "kế hoạch"},
        {"query": "báo cáo"},
    ]


async def test_a_call_is_listed_and_billed_while_the_script_still_runs(served):
    gate = asyncio.Event()
    held = [reading("paid_read", cost_usd=0.004, metered=True), waiting("slow_read", gate)]
    script = [
        completion(tool_calls=[running("print(tools.paid_read(), tools.slow_read())")]),
        completion("Xong."),
    ]
    app, _ = await scripting(served, script, extra_tools=held)

    sender = asyncio.create_task(say(app))
    await until(lambda: bool(listed(app)), timeout=10.0)

    # The script waits on its second call. The first is on the stored run already, and
    # paid for: one answer of the model at 0.001 and the read at 0.004.
    step, run = the_step(app), stored_run(app)
    assert step["ok"] is None and [call["name"] for call in step["calls"]] == ["paid_read"]
    assert run.status == RUNNING and run.spent_usd == pytest.approx(0.005)
    # And charged to the conversation, whose budget is counted on what it spent.
    assert app.runtime.store.get(app.conv.id).spent_usd == pytest.approx(0.005)
    gate.set()
    events = await asyncio.wait_for(sender, 10)

    assert the_result(events)["output"] == "paid_read slow_read"
    assert [call["name"] for call in the_step(app)["calls"]] == ["paid_read", "slow_read"]
    # Billed as it ended and not again with the result: 0.001 + 0.004 + 0.001.
    assert stored_run(app).spent_usd == pytest.approx(0.006)
    assert app.runtime.store.get(app.conv.id).spent_usd == pytest.approx(0.006)


async def test_the_calls_of_a_batch_are_sent_as_each_ends_and_kept_as_they_were_written(served):
    gate = asyncio.Event()
    source = dedent(
        """
        answers = tools.batch([{"tool": "slow_read"}, {"tool": "paid_read"}])
        print(answers[0]["output"], answers[1]["output"])
        """
    )
    held = [
        waiting("slow_read", gate, cost_usd=0.002, metered=True),
        reading("paid_read", cost_usd=0.004, metered=True),
    ]
    script = [completion(tool_calls=[running(source)]), completion("Xong.")]
    app, _ = await scripting(served, script, extra_tools=held)

    sender = asyncio.create_task(say(app))
    await until(lambda: bool(listed(app)), timeout=10.0)
    # The one written second ended first, and is shown without waiting for the other.
    assert [call["name"] for call in the_step(app)["calls"]] == ["paid_read"]
    gate.set()
    events = await asyncio.wait_for(sender, 10)

    sent = [event for event in events if event["type"] == "nested_call"]
    assert [(event["index"], event["call"]["name"]) for event in sent] == [
        (0, "paid_read"),
        (1, "slow_read"),
    ]
    assert [call["name"] for call in the_result(events)["calls"]] == ["slow_read", "paid_read"]
    assert [call["name"] for call in the_step(app)["calls"]] == ["slow_read", "paid_read"]
    # Two answers of the model at 0.001, and each read once.
    assert stored_run(app).spent_usd == pytest.approx(0.008)


def test_a_call_heard_twice_is_kept_once_and_billed_once():
    run = a_run()
    for _ in range(2):
        apply_event(run, NestedCallEvent("p1", 0, PAID), 10.5)
        apply_event(run, NestedCallEvent("p1", 1, UNPRICED), 10.6)

    [step] = run.steps
    assert step["calls"] == [PAID, UNPRICED] and step["ok"] is None
    assert run.spent_usd == pytest.approx(0.004) and run.unknown_cost_calls == 1


def test_the_result_bills_only_the_calls_no_event_listed_and_keeps_them_as_written():
    run = a_run()
    apply_event(run, NestedCallEvent("p1", 0, PAID), 10.5)
    apply_event(run, NestedCallEvent("p1", 1, UNPRICED), 10.6)
    written = [UNPRICED, OTHER, PAID, FREE]
    apply_event(run, ToolResultEvent("p1", SCRIPT_TOOL, True, "xong", calls=written), 11.0)

    [step] = run.steps
    assert step["calls"] == written and step["ok"] is True
    # 0.004 as it ended, 0.002 with the result; the unpriced one counted once.
    assert run.spent_usd == pytest.approx(0.006) and run.unknown_cost_calls == 1


def test_two_calls_that_read_alike_are_each_billed():
    run = a_run()
    apply_event(run, NestedCallEvent("p1", 0, PAID), 10.5)
    apply_event(run, ToolResultEvent("p1", SCRIPT_TOOL, True, "xong", calls=[PAID, PAID]), 11.0)

    assert run.spent_usd == pytest.approx(0.008)


def test_a_script_made_again_after_a_restart_lists_its_calls_afresh_and_pays_for_both_runs():
    run = a_run()
    apply_event(run, NestedCallEvent("p1", 0, PAID), 10.5)
    apply_event(run, NestedCallEvent("p1", 1, OTHER), 10.6)
    apply_event(run, ToolCallEvent("p1", SCRIPT_TOOL, {"script": "…"}), 20.0)

    [step] = run.steps
    assert "calls" not in step
    apply_event(run, NestedCallEvent("p1", 0, PAID), 20.5)
    assert step["calls"] == [PAID]
    apply_event(run, ToolResultEvent("p1", SCRIPT_TOOL, True, "xong", calls=[PAID]), 21.0)

    # What the cut run paid was paid: 0.004 + 0.002 then, 0.004 now.
    assert step["calls"] == [PAID] and run.spent_usd == pytest.approx(0.010)


def test_a_call_of_no_step_on_the_run_is_let_go():
    run = a_run()
    apply_event(run, NestedCallEvent("p9", 0, PAID), 10.5)

    [step] = run.steps
    assert "calls" not in step and run.spent_usd == 0


def test_the_event_is_sent_under_its_own_kind_with_the_call_whole():
    assert to_dict(NestedCallEvent("p1", 2, PAID)) == {
        "type": "nested_call",
        "tool_call_id": "p1",
        "index": 2,
        "call": PAID,
    }


async def test_a_turn_stopped_while_a_script_calls_has_charged_what_the_run_billed(served):
    """The script never comes to a result, and the calls it made were paid for all the same."""
    gate = asyncio.Event()
    held = [
        reading("paid_read", cost_usd=0.004, metered=True),
        reading("unpriced_read", metered=True),
        waiting("slow_read", gate),
    ]
    source = "print(tools.paid_read(), tools.unpriced_read(), tools.paid_read(), tools.slow_read())"
    script = [completion(tool_calls=[running(source)]), completion("Xong.")]
    app, _ = await scripting(served, script, extra_tools=held)

    sender = asyncio.create_task(say(app))
    await until(lambda: len(listed(app)) == 3, timeout=10.0)
    try:
        await app.client.post(app.stop)
        events = await asyncio.wait_for(sender, 10)
    finally:
        gate.set()

    assert not [event for event in events if event["type"] == "tool_result"]
    # One answer of the model at 0.001 and two reads at 0.004, on both ledgers alike.
    conv, run = app.runtime.store.get(app.conv.id), stored_run(app)
    assert run.spent_usd == pytest.approx(0.009) and run.unknown_cost_calls == 1
    assert conv.spent_usd == pytest.approx(0.009) and conv.unknown_cost_calls == 1


def nested(name: str, **paid: Any) -> NestedCall:
    return NestedCall(name=name, arguments={}, ok=True, output=name, ms=1, **paid)


def naming(name: str, told: list[NestedCall], named: list[NestedCall], **kind: Any) -> Tool:
    """A tool that tells `told` while it runs and whose result names `named`."""

    async def run(arguments: dict[str, Any]) -> ToolResult:
        for call in told:
            note_nested_call(call)
        return ToolResult(ok=True, output=name, calls=tuple(named))

    return Tool(name, f"Kể {name}.", {"type": "object", "properties": {}}, run, **kind)


async def test_a_call_the_result_names_that_was_never_told_is_charged_from_the_result(served):
    """One call is told and the result names two that read alike: each is paid for once."""
    paid, alike = (nested("paid", cost_usd=0.004, metered=True) for _ in range(2))
    quiet = naming("quiet", [paid], [paid, alike])
    script = [completion(tool_calls=[ToolCall("q1", "quiet", {})]), completion("Xong.")]
    app = served(script, extra_tools=[quiet])

    await say(app)

    # Two answers of the model at 0.001 and the two calls at 0.004, on both ledgers alike.
    conv, run = app.runtime.store.get(app.conv.id), stored_run(app)
    assert conv.spent_usd == pytest.approx(0.010) and run.spent_usd == pytest.approx(0.010)


async def test_calls_run_beside_each_other_are_charged_what_their_results_name(served):
    """Nothing listens to a call run beside others, so its result is all there is to charge."""
    paid = nested("paid", cost_usd=0.004, metered=True)
    beside = naming("beside", [paid], [paid], replay_safe=True, parallel=True)
    both = [ToolCall("b1", "beside", {}), ToolCall("b2", "beside", {})]
    app = served([completion(tool_calls=both), completion("Xong.")], extra_tools=[beside])

    await say(app)

    conv, run = app.runtime.store.get(app.conv.id), stored_run(app)
    assert conv.spent_usd == pytest.approx(0.010) and run.spent_usd == pytest.approx(0.010)


def test_only_a_call_that_paid_a_model_is_charged_and_one_with_no_price_is_counted_apart():
    store = Store(":memory:")
    conv = store.create()
    calls = [
        nested("paid", cost_usd=0.004, metered=True),
        nested("unpriced", metered=True),
        nested("free", cost_usd=0.5),
    ]

    charge_nested(store, conv.id, calls)

    charged = store.get(conv.id)
    assert charged.spent_usd == pytest.approx(0.004) and charged.unknown_cost_calls == 1


def test_the_calls_left_to_charge_are_those_of_the_result_that_were_never_told():
    paid, other = nested("paid", cost_usd=0.004, metered=True), nested("other", metered=True)

    assert not_yet_told([paid, other], [other, paid]) == []
    assert not_yet_told([paid, other], [other]) == [paid]
    assert not_yet_told([paid, other], []) == [paid, other]
    # Two calls that read alike are two calls: one told leaves the other to charge.
    assert not_yet_told([paid, nested("paid", cost_usd=0.004, metered=True)], [paid]) == [paid]


def telling(*names: str, gate: asyncio.Event | None = None, fail: bool = False) -> SimpleNamespace:
    """Deps whose one tool tells of `names` as calls it made, then waits on `gate`."""

    async def run(arguments: dict[str, Any]) -> str:
        for name in names:
            note_nested_call(nested(name))
        if gate is not None:
            await gate.wait()
        return "xong"

    tool = Tool("teller", "Kể.", {"type": "object", "properties": {}}, run)
    tools = ToolRegistry([tool])
    if fail:

        async def broken(name: str, arguments: dict[str, Any]) -> ToolResult:
            raise RuntimeError("hook hỏng")

        tools.execute = broken  # type: ignore[method-assign]
    store = Store(":memory:")
    return SimpleNamespace(tools=tools, store=store, conv_id=store.create().id)


def carrying(deps: SimpleNamespace, call_id: str = "t1") -> CallRun:
    return CallRun(deps, deps.conv_id, ToolCall(call_id, "teller", {}))


async def test_a_call_run_hands_on_what_was_told_in_order_and_then_its_result():
    run = carrying(telling("a", "b", "c"))

    said = [event async for event in run.events()]

    assert [(event.tool_call_id, event.index, event.call["name"]) for event in said] == [
        ("t1", 0, "a"),
        ("t1", 1, "b"),
        ("t1", 2, "c"),
    ]
    assert (run.result.ok, run.result.output) == (True, "xong")


async def test_a_call_told_is_charged_to_the_conversation_as_it_is_told_and_kept_as_told():
    gate = asyncio.Event()
    deps = telling(gate=gate)
    paid = [nested("a", cost_usd=0.004, metered=True), nested("b", cost_usd=0.002, metered=True)]

    async def run(arguments: dict[str, Any]) -> str:
        for call in paid:
            note_nested_call(call)
        await gate.wait()
        return "xong"

    deps.tools = ToolRegistry([Tool("teller", "Kể.", {"type": "object"}, run)])
    carried = carrying(deps)
    events = carried.events()
    try:
        assert (await anext(events)).call["name"] == "a"
        # The second is told and not yet handed on: charged is what was handed on.
        assert deps.store.get(deps.conv_id).spent_usd == pytest.approx(0.004)
        assert (await anext(events)).call["name"] == "b"
        assert deps.store.get(deps.conv_id).spent_usd == pytest.approx(0.006)
        assert carried.told == paid
    finally:
        gate.set()
    assert [event async for event in events] == []
    assert not_yet_told(paid, carried.told) == []


async def test_what_one_call_tells_is_not_heard_by_the_next_or_outside_any_call():
    first = carrying(telling("a"))
    second = carrying(telling(), "t2")

    assert [event.call["name"] for event in [e async for e in first.events()]] == ["a"]
    assert [e async for e in second.events()] == []
    note_nested_call(nested("nobody listens"))  # outside a call: said to no one, and no error


async def test_a_call_run_dropped_midway_cancels_the_call_and_waits_for_it_to_end():
    gate, ended = asyncio.Event(), []
    deps = telling("a", gate=gate)
    inner = deps.tools.get("teller").run

    async def watched(arguments: dict[str, Any]) -> str:
        try:
            return await inner(arguments)
        finally:
            ended.append("ended")

    deps.tools = ToolRegistry([Tool("teller", "Kể.", {"type": "object"}, watched)])
    run = carrying(deps)
    events = run.events()

    assert (await anext(events)).call["name"] == "a"
    try:  # bounded, so a call left running fails this test instead of hanging it
        await asyncio.wait_for(events.aclose(), 5)
    finally:
        gate.set()

    assert ended == ["ended"]
    with pytest.raises(asyncio.CancelledError):
        _ = run.result


async def test_a_turn_stopped_while_a_script_calls_ends_the_call_with_it():
    gate, ended = asyncio.Event(), []
    deps = telling(gate=gate)
    inner = deps.tools.get("teller").run

    async def watched(arguments: dict[str, Any]) -> str:
        try:
            return await inner(arguments)
        finally:
            ended.append("ended")

    deps.tools = ToolRegistry([Tool("teller", "Kể.", {"type": "object"}, watched)])
    run = carrying(deps)

    async def turn() -> None:
        async for _ in run.events():
            pass

    task = asyncio.create_task(turn())
    await asyncio.sleep(0.05)
    task.cancel()
    try:  # bounded, so a call left running fails this test instead of hanging it
        await asyncio.wait([task], timeout=5)
        assert task.cancelled() and ended == ["ended"]
    finally:
        gate.set()


async def test_what_a_call_raised_is_raised_where_its_result_is_read():
    run = carrying(telling(fail=True))

    assert [event async for event in run.events()] == []
    with pytest.raises(RuntimeError, match="hook hỏng"):
        _ = run.result
