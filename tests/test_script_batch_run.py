"""What the parent does with a batch a script asked for: calls that run side by side, never more
than `MAX_PARALLEL` of them at once, answered and kept for the run card in the order they were
written, each one passing through the agent's hooks and the registry as a call made alone does,
and none of them run when one is a call a script may not make (`script/tool.py`). Every script
here runs in a real child process; how the script asks is in `test_script_batch.py`."""

from __future__ import annotations

import asyncio
import json
from functools import partial
from typing import Any

from my_agent_crew import texts_script as t
from my_agent_crew.script import tool as script_module
from my_agent_crew.script.limits import MAX_BATCH, MAX_PARALLEL, RAW_LIMIT
from my_agent_crew.script.nested import ScriptRun
from my_agent_crew.script.replies import Answer
from my_agent_crew.script.runner import Outcome
from my_agent_crew.script.scope import SCRIPT_TOOL, unknown_tool, why_not
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_kit import TOOL_BLOCKED_BY_HOOK
from my_agent_crew.tools.registry import Tool, ToolError
from my_agent_crew.tools.result import ToolResult
from tests.test_script_tool import SCHEMA, Hooks, Reads, halted, toolbox, unfinished
from tests.test_script_tool import play as scripted

SHOWN = "print(json.dumps(answers))"
SIZES = 'print(json.dumps([len(answer["output"]) for answer in answers]))'


def one(name: str, **arguments: Any) -> str:
    """One call of a batch as a script writes it."""
    return json.dumps({"tool": name, "args": arguments})


def batch(*calls: str, show: str = SHOWN) -> str:
    return f"answers = tools.batch([{', '.join(calls)}])\n{show}"


def answered(result: ToolResult) -> list[dict[str, Any]]:
    """What a script that printed the answers of its batch was told."""
    assert result.ok, result.output
    return json.loads(result.output)


class Pauses:
    """Tools that stop for a while in the middle of a call, and keep how many of them were
    in the middle of one at the same time and in what order the calls ended."""

    def __init__(self) -> None:
        self.now = 0
        self.peak = 0
        self.ended: list[str] = []

    def tool(self, name: str, seconds: float = 0.05, answer: str = "xong") -> Tool:
        async def run(arguments: dict[str, Any]) -> str:
            self.now += 1
            self.peak = max(self.peak, self.now)
            try:
                await asyncio.sleep(seconds)
            finally:
                self.now -= 1
            self.ended.append(name)
            return answer

        return Tool(name, f"Đọc {name}.", SCHEMA, run, replay_safe=True)


# --- side by side ---


async def test_the_calls_of_a_batch_are_made_side_by_side():
    """Each waits for the other two to be under way before it answers: nothing is answered
    unless the three are made together."""
    barrier = asyncio.Barrier(3)

    async def meet(arguments: dict[str, Any]) -> str:
        await asyncio.wait_for(barrier.wait(), 10)
        return f"gặp {arguments['n']}"

    meeting = Tool("meet_read", "Đọc.", SCHEMA, meet, replay_safe=True)

    result = await scripted(toolbox(meeting), batch(*(one("meet_read", n=n) for n in range(3))))

    assert answered(result) == [{"ok": True, "output": f"gặp {n}"} for n in range(3)]


async def test_no_more_than_the_most_are_made_at_once_and_that_many_are():
    assert MAX_PARALLEL < MAX_BATCH
    pauses = Pauses()
    reading = pauses.tool("slow_read")

    result = await scripted(
        toolbox(reading), batch(*(one("slow_read", n=n) for n in range(MAX_BATCH)))
    )

    assert [one_answer["ok"] for one_answer in answered(result)] == [True] * MAX_BATCH
    assert (pauses.peak, pauses.now, len(pauses.ended)) == (MAX_PARALLEL, 0, MAX_BATCH)


async def test_the_answers_and_the_calls_kept_are_in_the_order_written_not_the_order_ended():
    """Written as neither the shortest nor the longest first, nor by name, nor the reverse of
    any of those: no other order a batch could be put in is this one."""
    pauses = Pauses()
    middle = pauses.tool("mid_read", 0.2, "vừa")
    slow, quick = pauses.tool("slow_read", 0.4, "chậm"), pauses.tool("quick_read", 0.0, "nhanh")

    result = await scripted(
        toolbox(middle, slow, quick), batch(one("mid_read"), one("slow_read"), one("quick_read"))
    )

    assert pauses.ended == ["quick_read", "mid_read", "slow_read"]
    assert answered(result) == [
        {"ok": True, "output": "vừa"},
        {"ok": True, "output": "chậm"},
        {"ok": True, "output": "nhanh"},
    ]
    assert [call.name for call in result.calls] == ["mid_read", "slow_read", "quick_read"]


async def test_a_call_is_timed_from_when_it_began_and_not_from_when_the_batch_was_asked():
    """The fifth call waits for the first of four that are made to end, and the wait is not
    a part of how long it took."""
    pauses = Pauses()
    slow = [pauses.tool(f"slow_{n}_read", 0.5) for n in range(MAX_PARALLEL)]
    quick = pauses.tool("quick_read", 0.0)

    result = await scripted(
        toolbox(*slow, quick), batch(*(one(tool.name) for tool in slow), one("quick_read"))
    )

    *slowly, last = result.calls
    assert [call.name for call in slowly] == [tool.name for tool in slow]
    assert all(480 <= call.ms < 2900 for call in slowly)
    assert last.name == "quick_read" and 0 <= last.ms < 450


# --- a batch cut short ---


async def test_a_batch_cut_short_keeps_the_calls_that_ended_in_the_order_written():
    """Whatever ends a script mid-batch, each call that ended was made: it is kept the moment
    it ends, where it was written, and the one still under way is not."""
    late, hung = asyncio.Event(), asyncio.Event()

    def waits_on(name: str, gate: asyncio.Event) -> Tool:
        async def run(arguments: dict[str, Any]) -> str:
            await gate.wait()
            return name

        return Tool(name, f"Đọc {name}.", SCHEMA, run, replay_safe=True)

    quick = Reads("quick_read", ToolResult(ok=True, output="nhanh", cost_usd=0.004, metered=True))
    made = ScriptRun(toolbox(waits_on("late_read", late), quick.tool, waits_on("hung_read", hung)))

    alone = await made.answer("quick_read", {})
    batch_of_three = asyncio.create_task(
        made.answer_many([("late_read", {}), ("quick_read", {}), ("hung_read", {})])
    )
    try:
        await asyncio.wait_for(_until(lambda: len(made.calls) == 2), 5)
        assert [call.name for call in made.calls] == ["quick_read", "quick_read"]
        late.set()
        await asyncio.wait_for(_until(lambda: len(made.calls) == 3), 5)
        batch_of_three.cancel()
        await asyncio.wait([batch_of_three], timeout=5)
    finally:
        hung.set()

    assert alone.ok and batch_of_three.cancelled()
    # The one that ended last was written first of the batch, and is kept there.
    assert [(call.name, call.cost_usd) for call in made.calls] == [
        ("quick_read", 0.004),
        ("late_read", None),
        ("quick_read", 0.004),
    ]
    assert made.received == len("nhanh") * 2 + len("late_read")


async def _until(ready) -> None:
    while not ready():
        await asyncio.sleep(0.005)


async def test_a_script_its_clock_ends_mid_batch_keeps_the_calls_it_made(monkeypatch):
    """The clock is shortened, so the script is ended while its last call still waits."""
    hung = asyncio.Event()

    async def wait(arguments: dict[str, Any]) -> str:
        await hung.wait()
        return "muộn"

    shortened = partial(script_module.run_script, total_s=1.5)
    monkeypatch.setattr(script_module, "run_script", shortened)
    priced = Reads("priced_read", ToolResult(ok=True, output="một", cost_usd=0.004, metered=True))
    waiting = Tool("hung_read", "Đọc.", SCHEMA, wait, replay_safe=True)
    source = (
        f"tools.priced_read()\n{batch(one('priced_read'), one('priced_read'), one('hung_read'))}"
    )

    try:
        result = await scripted(toolbox(priced.tool, waiting), source)
    finally:
        hung.set()

    assert not result.ok and t.SCRIPT_TIMED_OUT.format(seconds=1.5) in result.output
    assert [(call.name, call.cost_usd) for call in result.calls] == [("priced_read", 0.004)] * 3
    assert result.received_chars == len("một") * 3


# --- each call as a call made alone ---


async def test_a_call_that_failed_is_an_answer_of_its_own_and_the_others_are_made():
    first, gone = Reads("first_read", "một"), Reads("gone_read", ToolError("không có trang"))
    last = Reads("last_read", "ba")

    result = await scripted(
        toolbox(first.tool, gone.tool, last.tool),
        batch(one("first_read", n=1), one("gone_read"), one("last_read", n=3)),
    )

    assert answered(result) == [
        {"ok": True, "output": "một"},
        {"ok": False, "error": TOOL_FAILED.format(error="không có trang")},
        {"ok": True, "output": "ba"},
    ]
    assert (first.asked, last.asked) == ([{"n": 1}], [{"n": 3}])
    assert [(call.name, call.ok) for call in result.calls] == [
        ("first_read", True),
        ("gone_read", False),
        ("last_read", True),
    ]


async def test_a_name_that_is_no_tools_is_a_call_that_failed_and_is_not_one_kept():
    rows = Reads("rows_read", "dòng")

    result = await scripted(
        toolbox(rows.tool), batch(one("rows_read"), one("row_read"), one("rows_read"))
    )

    mistake = unknown_tool("row_read", [rows.tool])
    assert answered(result) == [
        {"ok": True, "output": "dòng"},
        {"ok": False, "error": mistake},
        {"ok": True, "output": "dòng"},
    ]
    assert "`rows_read`" in mistake
    assert len(rows.asked) == 2
    assert [call.name for call in result.calls] == ["rows_read", "rows_read"]


async def test_the_agents_hooks_are_asked_about_each_call_of_a_batch():
    rows, secret = Reads("rows_read", "ba dòng"), Reads("secret_read")
    hooks = Hooks(blocked=("secret_read",), noted=("rows_read",))

    result = await scripted(
        toolbox(rows.tool, secret.tool, hooks=hooks),
        batch(one("rows_read"), one("secret_read", path="két"), one("rows_read")),
    )

    blocked = TOOL_BLOCKED_BY_HOOK.format(name="secret_read", reason="không phải lúc")
    assert answered(result) == [
        {"ok": True, "output": "ba dòng [đã ghi sổ]"},
        {"ok": False, "error": blocked},
        {"ok": True, "output": "ba dòng [đã ghi sổ]"},
    ]
    assert secret.asked == [] and rows.asked == [{}, {}]
    assert hooks.arguments["secret_read"] == {"path": "két"}
    # Calls made together are told of as they begin and end: the script's own comes first and
    # last, and each of the others once before and, if it was made, once after.
    assert hooks.asked[0] == ("before", SCRIPT_TOOL) and hooks.asked[-1] == ("after", SCRIPT_TOOL)
    assert sorted(hooks.asked[1:-1]) == sorted(
        [("before", "rows_read")] * 2 + [("after", "rows_read")] * 2 + [("before", "secret_read")]
    )
    assert [(call.name, call.ok, call.output) for call in result.calls] == [
        ("rows_read", True, "ba dòng [đã ghi sổ]"),
        ("secret_read", False, blocked),
        ("rows_read", True, "ba dòng [đã ghi sổ]"),
    ]


async def test_each_answer_of_a_batch_is_handed_whole_up_to_what_a_script_is_handed():
    whole, over = Reads("whole_read", "x" * 150_000), Reads("over_read", "y" * 250_000)

    result = await scripted(
        toolbox(whole.tool, over.tool),
        batch(one("whole_read"), one("whole_read"), one("over_read"), show=SIZES),
    )

    # Together they are far more than a script is handed of one answer, and it is one answer
    # that is held to it.
    *kept, cut = answered(result)
    assert kept == [150_000, 150_000] and RAW_LIMIT - 10 <= cut <= RAW_LIMIT


async def test_each_call_of_a_batch_that_paid_a_model_carries_its_price():
    priced = Reads("priced_read", ToolResult(ok=True, output="một", cost_usd=0.004, metered=True))
    unpriced = Reads("unpriced_read", ToolResult(ok=True, output="hai", metered=True))
    free = Reads("free_read", ToolResult(ok=True, output="ba", cost_usd=0.5))

    result = await scripted(
        toolbox(priced.tool, unpriced.tool, free.tool),
        batch(one("priced_read"), one("unpriced_read"), one("free_read"), one("priced_read")),
    )

    assert [one_answer["output"] for one_answer in answered(result)] == ["một", "hai", "ba", "một"]
    assert [(call.name, call.cost_usd, call.metered) for call in result.calls] == [
        ("priced_read", 0.004, True),
        ("unpriced_read", None, True),
        ("free_read", None, False),
        ("priced_read", 0.004, True),
    ]


# --- a call a script may not make ---


async def test_a_batch_with_a_call_a_script_may_not_make_makes_none_and_ends_the_script():
    rows = Reads("rows_read")
    writes = Reads("notes_write", replay_safe=False)
    hooks = Hooks()

    result = await scripted(
        toolbox(rows.tool, writes.tool, hooks=hooks),
        f"""
        print("trước")
        try:
            tools.batch([{one("rows_read")}, {one("notes_write", text="x")}, {one("rows_read")}])
        except Exception:
            print("bắt được")
        print("sau")
        """,
    )

    reason = t.SCRIPT_ASKS_FIRST.format(name="notes_write", instead=t.SCRIPT_CALL_DIRECTLY)
    assert why_not(writes.tool) == reason
    assert (result.ok, result.output) == (False, unfinished("trước", halted(4, reason)))
    assert (rows.asked, writes.asked, result.calls) == ([], [], ())
    assert hooks.asked == [("before", SCRIPT_TOOL), ("after", SCRIPT_TOOL)]


async def test_of_several_calls_a_script_may_not_make_it_is_told_of_the_first_that_is_written():
    rows = Reads("rows_read")
    writes = Reads("notes_write", replay_safe=False)
    asks = Reads("always_asks", ask_reason=lambda arguments: "luôn hỏi")

    result = await scripted(
        toolbox(rows.tool, writes.tool, asks.tool),
        batch(one("nowhere"), one("always_asks"), one("notes_write"), one("rows_read")),
    )

    assert (result.ok, result.output) == (False, unfinished(halted(1, why_not(asks.tool) or "")))
    assert why_not(asks.tool) != why_not(writes.tool)
    assert (rows.asked, writes.asked, asks.asked, result.calls) == ([], [], [], ())


async def test_a_batch_that_may_not_be_made_is_answered_with_one_answer_to_each_call(monkeypatch):
    """The process a script runs in ends at the first answer that halts; one that was given
    fewer answers than it asked calls would not know which was which."""
    answers: list[Answer] = []

    async def asking(source, call, **limits):
        asked = [("rows_read", {}), ("notes_write", {}), ("nowhere", {}), ("rows_read", {})]
        answers.extend(await limits["call_many"](asked))
        return Outcome(True, "")

    monkeypatch.setattr(script_module, "run_script", asking)
    rows, writes = Reads("rows_read"), Reads("notes_write", replay_safe=False)

    await scripted(toolbox(rows.tool, writes.tool), "pass")

    skipped = Answer(False, t.SCRIPT_BATCH_NOT_RUN)
    assert answers == [
        skipped,
        Answer(False, why_not(writes.tool) or "", halt=True),
        skipped,
        skipped,
    ]
    assert (rows.asked, writes.asked) == ([], [])
