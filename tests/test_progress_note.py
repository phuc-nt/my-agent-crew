"""The progress note: a sentence the agent writes for whoever is watching a run."""

import asyncio

from my_agent_crew.activity.steps import apply_event
from my_agent_crew.agent.events import (
    AssistantMessageEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from my_agent_crew.store.runs import RUNNING, RunRecord
from my_agent_crew.tools.progress_note import (
    MAX_NOTE_CHARS,
    PROGRESS_NOTE_TOOL_NAME,
    build_progress_note_tool,
    note_text,
)


def fresh_run() -> RunRecord:
    return RunRecord("r1", "default", "c1", "chat", "t", RUNNING, "2026-09-23T08:00:00")


def note_call(text: str, call_id: str = "c1") -> ToolCallEvent:
    return ToolCallEvent(call_id, PROGRESS_NOTE_TOOL_NAME, {"text": text})


def test_a_note_becomes_its_own_step_not_a_tool_step():
    """A tool row would put a duration and an ok/fail mark on a sentence."""
    run = fresh_run()
    apply_event(run, note_call("Đang tìm hợp đồng"), 10.0)
    (step,) = run.steps
    assert step["kind"] == "note"
    assert step["text"] == "Đang tìm hợp đồng"
    assert "ok" not in step
    assert "tool_call_id" not in step


def test_a_note_is_closed_the_moment_it_is_written():
    """It is finished as soon as it is said, so nothing may render it as still running.

    The web decides "still open" by whether the internal clock key survives on the step,
    so leaving it open would spin a spinner on the note for the rest of the run.
    """
    run = fresh_run()
    apply_event(run, note_call("Đang chạy lệnh"), 10.0)
    (step,) = run.steps
    assert step["duration_ms"] == 0
    assert "_clock" not in step


def test_the_notes_result_adds_no_second_step():
    """The step was written by the call, and the result arrives after the fact.

    Without the guard the result finds no open tool step for this id and opens a new,
    empty one, so every note would show twice.
    """
    run = fresh_run()
    apply_event(run, note_call("Đang đọc tệp"), 10.0)
    result = ToolResultEvent("c1", PROGRESS_NOTE_TOOL_NAME, True, "Đã báo tiến trình.")
    apply_event(run, result, 10.1)
    assert [step["kind"] for step in run.steps] == ["note"]


def test_a_real_tool_still_becomes_a_tool_step():
    """The note branch keys off the tool name, so it must not swallow anything else."""
    run = fresh_run()
    apply_event(run, ToolCallEvent("c1", "workspace_list", {"path": "."}), 10.0)
    apply_event(run, ToolResultEvent("c1", "workspace_list", True, "a.txt"), 11.0)
    (step,) = run.steps
    assert step["kind"] == "tool" and step["ok"] is True and step["duration_ms"] == 1000


def test_a_note_between_tool_calls_leaves_them_intact():
    """The note must not be mistaken for the open tool step a later result closes."""
    run = fresh_run()
    apply_event(run, ToolCallEvent("t1", "shell_run", {}), 10.0)
    apply_event(run, note_call("Đang đợi lệnh chạy", "n1"), 10.5)
    apply_event(run, ToolResultEvent("t1", "shell_run", True, "ok"), 12.0)
    tool, note = run.steps
    assert tool["kind"] == "tool" and tool["duration_ms"] == 2000 and tool["ok"] is True
    assert note["kind"] == "note" and note["duration_ms"] == 0


def test_a_note_does_not_break_the_model_step_it_follows():
    """A model step is matched by being last and still open.

    A note pushed between the message and its close would take that place, and the
    model step would be duplicated rather than completed.
    """
    run = fresh_run()
    call = {"id": "c1", "name": PROGRESS_NOTE_TOOL_NAME, "arguments": {"text": "Đang làm"}}
    apply_event(run, AssistantMessageEvent(1, "để tôi xem", [call], "p", "m", 0.001), 10.0)
    apply_event(run, note_call("Đang làm"), 10.1)
    kinds = [step["kind"] for step in run.steps]
    assert kinds == ["model", "note"]


def test_a_long_note_is_cut_rather_than_refused():
    """A formatting slip should shorten the note, not fail the turn."""
    run = fresh_run()
    apply_event(run, note_call("a" * 500), 10.0)
    (step,) = run.steps
    assert len(step["text"]) == MAX_NOTE_CHARS


def test_a_note_is_collapsed_to_one_line():
    """It occupies a single timeline row, so newlines would break the row it sits in."""
    assert note_text({"text": "  đang   tìm\n\ntài liệu  "}) == "đang tìm tài liệu"


def test_a_missing_text_is_empty_rather_than_an_error():
    assert note_text({}) == ""


def test_the_tool_never_pauses_for_approval():
    """A note approved after the fact describes work already decided."""
    tool = build_progress_note_tool()
    assert tool.requires_approval is False
    assert tool.name == PROGRESS_NOTE_TOOL_NAME


def test_an_empty_note_tells_the_model_nothing_was_shown():
    """Otherwise the model assumes the person saw something they did not."""
    tool = build_progress_note_tool()
    said = asyncio.run(tool.run({"text": "Đang tải"}))
    silent = asyncio.run(tool.run({"text": "   "}))
    assert said != silent
