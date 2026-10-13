"""A tool that stops for a person only for some of its calls, and one whose calls the owner's
settings mark routine: where the two sit in the gate's order, that a tool crashing while it
decides never lets a call through, and that a script and a request read back later are given
the same answer as the turn."""

from __future__ import annotations

from typing import Any

import pytest

from my_agent_crew import texts_script as t
from my_agent_crew.agent.events import ApprovalRequiredEvent, DoneEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.tool_gate import ASK, RUN, ask_reason_text, verdict
from my_agent_crew.agent.turn_context import (
    reading_as,
    set_turn_conversation,
    turn_conversation_id,
)
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.script.gate import job_gate, script_gate
from my_agent_crew.script.scope import only_reads
from my_agent_crew.server.routes_conversations import conversation_detail
from my_agent_crew.texts import SHELL_ASK_REASON
from my_agent_crew.tools.registry import Tool
from tests.conftest import collect

NAME = "page_click"
SCHEMA = {"type": "object", "properties": {"button": {"type": "string"}}}
PAY, NEXT = {"button": "Thanh toán"}, {"button": "Tiếp"}
REASON = "Nút «Thanh toán» cần người duyệt."


def crash(arguments: dict[str, Any]) -> Any:
    raise RuntimeError("no page")


def asks_on_pay(arguments: dict[str, Any]) -> str | None:
    return REASON if arguments.get("button") == "Thanh toán" else None


def routine_on_next(arguments: dict[str, Any]) -> bool:
    return arguments.get("button") == "Tiếp"


class Clicks:
    """A tool that changes things and keeps what it was handed, so a test knows whether a
    call reached it."""

    def __init__(self, **gate: Any) -> None:
        self.ran: list[dict[str, Any]] = []
        self.tool = Tool(NAME, "Bấm nút.", SCHEMA, self._run, requires_approval=True, **gate)

    async def _run(self, arguments: dict[str, Any]) -> str:
        self.ran.append(arguments)
        return "đã bấm"


def gate_of(deps_factory, **gate: Any):
    deps = deps_factory(extra_tools=[Clicks(**gate).tool])

    def said(arguments: dict[str, Any], **allowed: Any) -> str:
        return verdict(deps, deps.store.create(**allowed), NAME, arguments)

    return deps, said


def test_a_call_the_tool_names_asks_whatever_the_conversation_allows(deps_factory):
    deps, said = gate_of(deps_factory, ask_when=asks_on_pay)

    assert said(PAY, autonomous=True) == ASK
    assert said(PAY, autonomous=False) == ASK
    always = deps.store.update(deps.store.create(autonomous=True).id, auto_approve=(NAME,))
    assert verdict(deps, always, NAME, PAY) == ASK


def test_a_call_the_tool_does_not_name_is_left_to_the_ordinary_rules(deps_factory):
    deps, said = gate_of(deps_factory, ask_when=asks_on_pay)

    assert said(NEXT, autonomous=True) == RUN
    assert said(NEXT, autonomous=False) == ASK
    always = deps.store.update(deps.store.create().id, auto_approve=(NAME,))
    assert verdict(deps, always, NAME, NEXT) == RUN


@pytest.mark.parametrize("empty", [None, ""])
def test_no_reason_is_no_reason_and_not_a_stop(deps_factory, empty):
    deps, said = gate_of(deps_factory, ask_when=lambda arguments: empty)

    assert said(PAY, autonomous=True) == RUN
    assert ask_reason_text(deps, NAME, PAY) == ""


def test_the_reason_is_shown_as_the_tool_wrote_it(deps_factory):
    deps, _ = gate_of(deps_factory, ask_when=asks_on_pay)

    assert ask_reason_text(deps, NAME, PAY) == REASON
    assert ask_reason_text(deps, NAME, NEXT) == ""
    assert SHELL_ASK_REASON.format(pattern=REASON) != REASON


def test_a_tool_that_crashes_deciding_whether_to_ask_still_asks(deps_factory):
    deps, said = gate_of(deps_factory, ask_when=crash)

    assert said(NEXT, autonomous=True) == ASK
    assert ask_reason_text(deps, NAME, NEXT) == NAME


def test_a_routine_call_runs_in_a_conversation_that_is_supervised(deps_factory):
    _, said = gate_of(deps_factory, allow_when=routine_on_next)

    assert said(NEXT, autonomous=False) == RUN
    assert said(PAY, autonomous=False) == ASK
    assert said(PAY, autonomous=True) == RUN


def test_a_tool_that_crashes_deciding_what_is_routine_allowed_nothing(deps_factory):
    _, said = gate_of(deps_factory, allow_when=crash)

    assert said(NEXT, autonomous=False) == ASK
    # Autonomy is the person's own word and is not the tool's to take back.
    assert said(NEXT, autonomous=True) == RUN


def test_a_reason_to_ask_outranks_what_is_routine(deps_factory):
    _, said = gate_of(deps_factory, ask_when=asks_on_pay, allow_when=lambda arguments: True)

    assert said(PAY, autonomous=False) == ASK
    assert said(PAY, autonomous=True) == ASK
    assert said(NEXT, autonomous=False) == RUN


def test_neither_rule_is_read_for_a_tool_that_changes_nothing(deps_factory):
    """Both are rules of the approval gate, and a tool that never meets it has no use for
    them: nothing here turns a reader into a tool that asks."""
    reader = Tool(NAME, "Đọc.", SCHEMA, Clicks()._run, ask_when=asks_on_pay, allow_when=crash)
    deps = deps_factory(extra_tools=[reader])

    assert verdict(deps, deps.store.create(), NAME, PAY) == RUN


async def test_a_turn_nobody_watches_pauses_on_the_call_the_tool_names(deps_factory):
    clicks = Clicks(ask_when=asks_on_pay)
    calls = (ToolCall("c1", NAME, NEXT), ToolCall("c2", NAME, PAY))
    deps = deps_factory(
        script=[completion(tool_calls=calls), completion("xong")], extra_tools=[clicks.tool]
    )
    conv = deps.store.create(autonomous=True)

    events = await collect(run_turn(deps, conv.id, "mua giúp"))

    pause = events[-1]
    assert isinstance(pause, ApprovalRequiredEvent)
    assert (pause.name, pause.arguments, pause.reason) == (NAME, PAY, REASON)
    assert clicks.ran == [NEXT]


async def test_a_turn_nobody_watches_runs_the_calls_the_tool_does_not_name(deps_factory):
    clicks = Clicks(ask_when=asks_on_pay)
    deps = deps_factory(
        script=[completion(tool_calls=(ToolCall("c1", NAME, NEXT),)), completion("xong")],
        extra_tools=[clicks.tool],
    )
    conv = deps.store.create(autonomous=True)

    events = await collect(run_turn(deps, conv.id, "xem tiếp"))

    assert isinstance(events[-1], DoneEvent)
    assert clicks.ran == [NEXT]


async def test_a_request_read_back_later_gives_the_reason_the_turn_gave(deps_factory):
    """A reason may depend on the conversation, as the page a browser tab shows does. The
    turn knows its conversation; a reload that reads the request back is told which."""

    def asks_by_conversation(arguments: dict[str, Any]) -> str | None:
        return f"trang của {turn_conversation_id() or 'không ai'}"

    clicks = Clicks(ask_when=asks_by_conversation)
    deps = deps_factory(
        script=[completion(tool_calls=(ToolCall("c1", NAME, PAY),))], extra_tools=[clicks.tool]
    )
    conv = deps.store.create(autonomous=True)

    events = await collect(run_turn(deps, conv.id, "mua giúp"))
    set_turn_conversation("")  # the reload is another request: no turn of this conversation

    assert events[-1].reason == f"trang của {conv.id}"
    assert conversation_detail(deps, conv.id)["pending_approval"]["reason"] == events[-1].reason
    assert turn_conversation_id() == ""


def test_reading_as_puts_back_the_conversation_that_was_there():
    set_turn_conversation("outer")

    with reading_as("inner"):
        assert turn_conversation_id() == "inner"

    assert turn_conversation_id() == "outer"
    set_turn_conversation("")


def test_a_script_is_ended_by_the_call_the_tool_names_without_repeating_its_reason(deps_factory):
    deps, _ = gate_of(deps_factory, ask_when=asks_on_pay)
    conv = deps.store.create(autonomous=True)
    set_turn_conversation(conv.id)
    try:
        refusal = script_gate(deps)

        assert refusal(NAME, PAY) == t.SCRIPT_GATE_ASKS.format(name=NAME)
        assert REASON not in refusal(NAME, PAY)
        assert refusal(NAME, NEXT) is None
    finally:
        set_turn_conversation("")


def test_a_script_makes_a_routine_call_in_a_conversation_that_is_supervised(deps_factory):
    deps, _ = gate_of(deps_factory, allow_when=routine_on_next)
    conv = deps.store.create(autonomous=False)
    set_turn_conversation(conv.id)
    try:
        refusal = script_gate(deps)

        assert refusal(NAME, NEXT) is None
        assert refusal(NAME, PAY) == t.SCRIPT_GATE_ASKS.format(name=NAME)
    finally:
        set_turn_conversation("")


def test_the_script_of_a_schedule_is_ended_by_the_call_the_tool_names(deps_factory):
    deps, _ = gate_of(deps_factory, ask_when=asks_on_pay)

    refusal = job_gate(deps)

    assert refusal(NAME, PAY) == t.SCRIPT_GATE_ASKS.format(name=NAME)
    assert refusal(NAME, NEXT) is None


def test_a_tool_that_may_ask_is_never_counted_among_the_ones_that_only_read():
    run = Clicks()._run
    reader = Tool(NAME, "Đọc.", SCHEMA, run, replay_safe=True)
    may_ask = Tool(NAME, "Đọc.", SCHEMA, run, replay_safe=True, ask_when=asks_on_pay)

    assert only_reads(reader)
    assert not only_reads(may_ask)
