"""A turn that keeps making the same tool calls is told so, then halted before it burns
its whole step limit; work that repeats a command with changes in between is left alone."""

from __future__ import annotations

import pytest

from my_agent_crew import texts
from my_agent_crew.agent.events import HaltedEvent, ToolResultEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.loop_guard import HALT, OK, REDIRECT, LoopGuard
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.tools import Tool
from my_agent_crew.turn_reply import collect_reply
from tests.conftest import collect


def call(name: str = "shell_run", **arguments) -> dict:
    return {"id": f"id-{len(arguments)}", "name": name, "arguments": arguments}


def verdicts(guard: LoopGuard, turns: list[list[dict]]) -> list[str]:
    return [guard.observe(turn) for turn in turns]


def test_the_third_identical_call_in_a_row_is_told_and_the_sixth_halts():
    same = [call(command="pytest")]

    assert verdicts(LoopGuard(), [same] * 6) == [OK, OK, REDIRECT, OK, OK, HALT]


def test_a_changed_argument_starts_the_count_over():
    a, b = [call(command="pytest")], [call(command="pytest -x")]

    assert verdicts(LoopGuard(), [a, a, b, a, a, b]) == [OK] * 6


def test_calls_that_take_turns_are_never_a_loop():
    a, b = [call(command="pytest")], [call(name="workspace_read", path="app.py")]

    assert verdicts(LoopGuard(), [a, b] * 6) == [OK] * 12


def test_a_note_or_a_question_between_repeats_starts_the_count_over():
    a = [call(command="pytest")]
    note = [call(name="progress_note", text="đang thử lại")]
    asked = [call(name="ask_user", question="Chạy tiếp?")]
    reply: list[dict] = []

    for between in (note, asked, reply):
        assert verdicts(LoopGuard(), [a, a, between, a, a]) == [OK] * 5


def test_a_note_beside_the_repeated_call_does_not_hide_the_repeat():
    turns = [
        [call(name="progress_note", text=f"lần {i}"), call(command="pytest")] for i in range(3)
    ]

    assert verdicts(LoopGuard(), turns)[-1] == REDIRECT


def test_parallel_calls_in_another_order_are_the_same_call():
    a = call(command="pytest")
    b = {"id": "x", "name": "workspace_read", "arguments": {"path": "app.py", "limit": 20}}
    b_again = {"id": "y", "name": "workspace_read", "arguments": {"limit": 20, "path": "app.py"}}

    assert verdicts(LoopGuard(), [[a, b], [b_again, a], [a, b]])[-1] == REDIRECT


def test_a_new_message_from_the_person_starts_the_count_over():
    same, guard = [call(command="pytest")], LoopGuard()
    verdicts(guard, [same, same])

    guard.reset()

    assert verdicts(guard, [same, same]) == [OK, OK]


def repeating(times: int) -> list:
    return [
        completion(tool_calls=(ToolCall(f"c{i}", "count_up", {"what": "bài"}),))
        for i in range(times)
    ]


def counter(name: str = "count_up") -> tuple[Tool, list[int]]:
    runs: list[int] = []

    async def count_up(args: dict) -> str:
        runs.append(1)
        return f"lỗi lần {len(runs)}: không kết nối được"

    return Tool(name, "Đếm.", {"type": "object", "properties": {}}, count_up), runs


async def test_a_turn_that_repeats_itself_is_told_once_then_halted_before_the_last_call_runs(
    deps_factory,
):
    tool, runs = counter()
    deps = deps_factory(script=repeating(10), extra_tools=[tool], max_steps=20)
    conv = deps.store.create()

    events = await collect(run_turn(deps, conv.id, "đếm bài"))

    assert events[-1] == HaltedEvent(reason="loop", spent_usd=pytest.approx(0.006))
    requests = deps.chain.providers["scripted"].requests
    assert len(requests) == 6
    assert len(runs) == 5  # the sixth call was refused, not run
    refused = [e for e in events if isinstance(e, ToolResultEvent)][-1]
    assert refused.tool_call_id == "c5" and not refused.ok
    assert refused.output == texts.LOOP_HALTED_TOOL
    history = [m.message for m in deps.store.history(conv.id)]
    notes = [i for i, m in enumerate(history) if texts.LOOP_REDIRECT[:10] in m.content]
    assert len(notes) == 1
    # After the third call's result and before the fourth model call.
    before, note, after = history[notes[0] - 1], history[notes[0]], history[notes[0] + 1]
    assert before.role == "tool" and before.tool_call_id == "c2"
    assert note.role == "user" and after.role == "assistant"
    # It speaks in the person's role, so it names the tool and quotes nothing it was given
    # or returned: a fetched page must never come back to the model as the person's words.
    assert note.content == texts.LOOP_REDIRECT.format(names="count_up", count=3)
    assert "bài" not in note.content and "không kết nối được" not in note.content
    assert requests[3].messages[-1].content == note.content
    # Every call the model made has a result, so the conversation can carry on.
    asked = {c.id for m in history if m.role == "assistant" for c in m.tool_calls}
    answered = {m.tool_call_id for m in history if m.role == "tool"}
    assert asked == answered


async def test_a_turn_that_changes_course_after_the_reminder_carries_on(deps_factory):
    tool, runs = counter()
    script = [*repeating(3), completion("Máy chủ không phản hồi, bạn kiểm tra giúp mạng nhé.")]
    deps = deps_factory(script=script, extra_tools=[tool], max_steps=20)
    conv = deps.store.create()

    reply = await collect_reply(run_turn(deps, conv.id, "đếm bài"))

    assert reply.status == "done" and len(runs) == 3
    assert reply.text == "Máy chủ không phản hồi, bạn kiểm tra giúp mạng nhé."


async def test_running_the_tests_fixing_and_running_them_again_is_not_a_loop(deps_factory):
    tests, runs = counter("run_tests")
    fix, _ = counter("fix")
    script = [
        completion(tool_calls=(ToolCall(f"{name}{i}", name, {"path": "app.py"}),))
        for i in range(4)
        for name in ("run_tests", "fix")
    ]
    deps = deps_factory(
        script=[*script, completion("Xong.")], extra_tools=[tests, fix], max_steps=20
    )
    conv = deps.store.create()

    reply = await collect_reply(run_turn(deps, conv.id, "sửa cho test xanh"))

    assert reply.status == "done" and len(runs) == 4
    history = deps.store.history(conv.id)
    assert not any(texts.LOOP_REDIRECT[:10] in m.message.content for m in history)


async def test_a_loop_halt_reads_as_words_where_a_person_reads_it(deps_factory):
    tool, _ = counter()
    deps = deps_factory(script=repeating(6), extra_tools=[tool], max_steps=20)
    conv = deps.store.create()

    reply = await collect_reply(run_turn(deps, conv.id, "đếm bài"))

    assert reply.status == "halted"
    assert texts.REPLY_HALTED.format(reason=texts.HALT_REASONS["loop"], spent=0.006) in reply.text
    assert "(loop)" not in reply.text
