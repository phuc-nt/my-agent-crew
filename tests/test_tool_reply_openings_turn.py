"""The replies a turn itself fails a call with, before any tool runs: arguments that were not
valid or were cut off, a turn out of steps, a turn stopped for repeating itself, an id already
approved for another call. Each goes out as a failure and is stored word for word, and the
stored words are all a thread read back has, so each must open as the web expects of it
(`web/src/lib/tool-reply.ts`)."""

from __future__ import annotations

from typing import Any

import pytest

from my_agent_crew.agent.events import HaltedEvent, ToolResultEvent
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.agent.resume import resolve_approval
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.tool_call_buffer import CUT_OFF
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.texts import (
    APPROVAL_CALL_MISMATCH,
    LOOP_HALTED_TOOL,
    STEPS_HALTED_TOOL,
    TOOL_ARGS_CUT_OFF,
    TOOL_ARGS_INVALID,
)
from my_agent_crew.tools import Tool
from tests.conftest import collect
from tests.test_tool_reply_openings import fixed_words, web_failed

BROKEN = "40 chars; Unterminated string starting at char 12"
WRITE = ToolCall("c1", "workspace_write", {"path": "out.txt", "content": "một"})
OTHER_WRITE = ToolCall("c1", "workspace_write", {"path": "out.txt", "content": "khác"})


def _spy(ran: list[str]) -> Tool:
    async def run(args: dict[str, Any]) -> str:
        ran.append("spy")
        return "ok"

    return Tool("spy", "", {"type": "object", "properties": {}}, run)


def _spy_calls(times: int) -> list:
    return [completion(tool_calls=(ToolCall(f"c{i}", "spy", {}),)) for i in range(times)]


def _last_result(events: list) -> ToolResultEvent:
    return [event for event in events if isinstance(event, ToolResultEvent)][-1]


def _failed_as_the_web_reads_it(
    deps: AgentDeps, conv_id: str, result: ToolResultEvent, template: str
) -> None:
    """The reply went out as a failure, it opens with the web's opening for its sentence, and
    the thread holds it word for word under the call's id."""
    opening = fixed_words(template)
    assert result.ok is False
    assert opening in web_failed() and result.output.startswith(opening)
    stored = [
        held.message.content
        for held in deps.store.history(conv_id)
        if held.message.role == "tool" and held.message.tool_call_id == result.tool_call_id
    ]
    assert stored[-1] == result.output


@pytest.mark.parametrize(
    ("detail", "template"),
    [(BROKEN, TOOL_ARGS_INVALID), (CUT_OFF + "51 chars; cut off at char 51", TOOL_ARGS_CUT_OFF)],
)
async def test_a_call_whose_arguments_never_parsed_opens_as_the_web_expects(
    deps_factory, detail: str, template: str
):
    broken = ToolCall("c1", "workspace_list", {}, invalid=detail)
    deps = deps_factory(script=[completion(tool_calls=(broken,)), completion("xong")])
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "liệt kê"))

    result = _last_result(events)
    assert result.output == template.format(name="workspace_list", detail=detail)
    _failed_as_the_web_reads_it(deps, conv.id, result, template)


async def test_the_call_a_turn_out_of_steps_never_ran_opens_as_the_web_expects(deps_factory):
    ran: list[str] = []
    script = [*_spy_calls(3), completion("Chào.")]
    deps = deps_factory(script=script, extra_tools=[_spy(ran)], max_steps=3)
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "go"))

    assert isinstance(events[-1], HaltedEvent) and events[-1].reason == "max_steps"
    result = _last_result(events)
    assert result.output == STEPS_HALTED_TOOL and ran == ["spy", "spy"]
    _failed_as_the_web_reads_it(deps, conv.id, result, STEPS_HALTED_TOOL)


async def test_the_call_a_turn_is_stopped_at_for_repeating_itself_opens_as_the_web_expects(
    deps_factory,
):
    ran: list[str] = []
    deps = deps_factory(script=_spy_calls(10), extra_tools=[_spy(ran)], max_steps=20)
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đếm bài"))

    assert isinstance(events[-1], HaltedEvent) and events[-1].reason == "loop"
    result = _last_result(events)
    assert result.output == LOOP_HALTED_TOOL and len(ran) == 5
    _failed_as_the_web_reads_it(deps, conv.id, result, LOOP_HALTED_TOOL)


async def test_a_call_whose_id_was_approved_for_another_opens_as_the_web_expects(deps_factory):
    deps = deps_factory(
        script=[
            completion(tool_calls=(WRITE,)),
            completion("đã ghi"),
            completion(tool_calls=(OTHER_WRITE,)),
            completion("xong"),
        ]
    )
    conv = deps.store.create()
    paused = await collect(run_turn(deps, conv.id, "ghi file"))
    await collect(resolve_approval(deps, conv.id, paused[-1].approval_id, approve=True))

    resumed = await collect(run_turn(deps, conv.id, "ghi lại"))

    result = next(event for event in resumed if isinstance(event, ToolResultEvent))
    assert result.output == APPROVAL_CALL_MISMATCH
    assert (deps.settings.workspace_dir / "out.txt").read_text(encoding="utf-8") == "một"
    _failed_as_the_web_reads_it(deps, conv.id, result, APPROVAL_CALL_MISMATCH)
