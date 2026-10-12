"""How much of what a call said its step keeps (`activity/step_previews.py`).

A call that went well is kept as a glance. One that failed is read by whoever has to put
it right, and what to do about it is often the last thing it said: a refusal ends on the
way round it, a call that did not fit on how the tool is called. So a failure is kept whole
while it is short, and by its head and its tail when it is not.
"""

from __future__ import annotations

from typing import Any

import pytest

from my_agent_crew import texts_script as t
from my_agent_crew.activity.steps import apply_event
from my_agent_crew.agent.events import (
    AssistantMessageEvent,
    RouteFallbackEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.tools.registry import Tool, ToolError
from tests.test_activity import fresh_run
from tests.test_script_discovery import HOW, PAGES
from tests.test_script_model_calls import Model, asking
from tests.test_script_tool import Reads, play, toolbox

GLANCE = "x" * 160 + "…"
# What a refusal of the approval gate ends on: the one thing its reader can do about it.
WAY_ROUND = "Gọi `shell_run` trực tiếp, ngoài script, để người dùng được hỏi."


def closed(ok: bool, said: str) -> dict[str, Any]:
    """The step of a tool call that ended `ok` saying `said`."""
    run = fresh_run()
    apply_event(run, ToolCallEvent("c1", "shell_run", {"command": "make"}), 10.0)
    apply_event(run, ToolResultEvent("c1", "shell_run", ok, said), 10.5)
    return run.steps[-1]


def test_a_step_that_failed_keeps_what_it_said_whole_while_it_is_short_enough_to_read():
    assert closed(False, "x" * 161)["output"] == "x" * 161
    assert closed(False, "x" * 600)["output"] == "x" * 600


def test_a_longer_failure_is_kept_by_its_head_and_its_tail():
    said = "a" * 250 + "b" * 300 + "c" * 450

    kept = closed(False, said)["output"]

    assert kept == "a" * 200 + "…" + "c" * 400
    # One character past what is kept whole is already cut, and never to more than that.
    assert closed(False, "a" * 201 + "c" * 400)["output"] == "a" * 200 + "…" + "c" * 400


def test_what_a_refusal_ends_on_outlives_the_cut():
    said = "Lỗi: script dừng ở dòng 3. " + "đã đọc 40 dòng. " * 60 + WAY_ROUND

    kept = closed(False, said)["output"]

    assert len(kept) == 601 and kept.endswith(WAY_ROUND)
    assert kept.startswith("Lỗi: script dừng ở dòng 3. ")


def test_a_failure_is_measured_as_the_one_line_it_is_kept_as():
    said = "\n".join(["dòng   hỏng\t\tở đây"] * 37)

    kept = closed(False, said)["output"]

    # Past what is kept whole as it was written, and within it once each gap is one space.
    assert (len(said), len(kept)) == (702, 591)
    assert kept == " ".join(["dòng hỏng ở đây"] * 37)


def test_a_step_that_went_well_is_kept_as_the_glance_it_was():
    assert closed(True, "x" * 161)["output"] == GLANCE
    assert closed(True, "x" * 600)["output"] == GLANCE


async def test_a_call_of_a_script_that_failed_keeps_how_the_tool_is_called():
    """How it is called comes after the tool's own words, so a cut from the front alone
    kept the complaint and dropped the answer to it."""

    async def run(arguments: dict[str, Any]) -> str:
        raise ToolError("thiếu tham số. " + "xem lại lời gọi. " * 40)

    registry = toolbox(Tool("pages_read", "Tìm trang.", PAGES, run, replay_safe=True))

    result = await play(
        registry,
        """
        try:
            tools.pages_read(colour="red")
        except Exception:
            print("bắt được")
        """,
    )

    [call] = result.calls
    assert (result.output, call.ok) == ("bắt được", False)
    assert call.output.endswith(HOW) and "…" in call.output
    assert call.output.startswith(TOOL_FAILED.format(error="thiếu tham số."))
    assert len(call.output) == 601


async def test_a_call_of_a_script_that_went_well_is_kept_as_a_glance():
    result = await play(toolbox(Reads("rows_read", "x" * 600).tool), "tools.rows_read()")

    assert [(call.ok, call.output) for call in result.calls] == [(True, GLANCE)]


async def test_an_asking_that_failed_keeps_why_past_a_glance():
    """What an upstream said of itself is for the person who reads the run card, and the
    part that names what went wrong is not always at the front."""
    upstream = "503 from upstream. " + "thử lại. " * 30 + "hết hạn mức hôm nay."
    source = """
        try:
            llm.classify("mua ngay kẻo hết", ["rác", "thường"])
        except Exception:
            print("bắt được")
        """

    result = await play(asking(Model(ProviderError(upstream))), source)

    [call] = result.calls
    assert (result.output, call.ok) == ("bắt được", False)
    assert 161 < len(call.output) <= 601 and call.output.endswith("hết hạn mức hôm nay.")


@pytest.mark.parametrize("length", [161, 700])
def test_a_route_that_was_passed_over_is_still_kept_as_a_glance(length):
    """The call went on to the next route: nothing ended there, and a run that tries
    several routes keeps one such line for each."""
    run = fresh_run()
    apply_event(run, RouteFallbackEvent("openrouter", "glm", "x" * length), 10.0)

    assert run.steps[-1]["error"] == GLANCE


def test_what_the_model_said_is_still_kept_as_a_glance():
    run = fresh_run()
    apply_event(run, AssistantMessageEvent(1, "x" * 700, [], "p", "m", None), 10.0)

    assert run.steps[-1]["preview"] == GLANCE


def test_the_refusals_of_the_approval_gate_end_on_the_way_round_them():
    """Which is why the tail is kept: were the wording turned about, the way round would
    be at the head and the tests above would say less than they claim."""
    asks = t.SCRIPT_GATE_ASKS.format(name="shell_run")
    listed = t.SCRIPT_GATE_ASK_LIST.format(name="shell_run", pattern="rm -rf")

    assert asks.endswith(WAY_ROUND) and listed.endswith(WAY_ROUND)
