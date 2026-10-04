"""A canvas write is one long argument, and nothing of it could be shown until the model had
finished writing it. The preview lets the pieces of the two tools that write a whole document
through as events: the first at once, so a card can say a document is on its way, then what
gathered since, no more often than the interval. Every other tool's arguments stay on the server."""

from __future__ import annotations

import inspect
import time

import pytest

from my_agent_crew.agent.draft_preview import DRAFT_TOOLS, DraftPreview
from my_agent_crew.agent.events import ToolCallDeltaEvent
from my_agent_crew.llm.types import ToolCallDelta

OTHER_TOOLS = ("artifact_import", "artifact_edit", "workspace_write", "shell_run")


class Clock:
    """Reads what the test last set, so a test says how far apart two pieces came."""

    def __init__(self, now: float = 0.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


def piece(chunk: str, name: str = "artifact_create", index: int = 0) -> ToolCallDelta:
    return ToolCallDelta(index=index, name=name, chunk=chunk)


def shown(chunk: str, name: str = "artifact_create", index: int = 0, attempt: int = 0):
    return ToolCallDeltaEvent(index=index, name=name, chunk=chunk, attempt=attempt)


def test_the_tools_previewed_are_the_two_that_write_a_whole_document():
    assert DRAFT_TOOLS == frozenset({"artifact_create", "artifact_rewrite"})


@pytest.mark.parametrize("name", ["artifact_create", "artifact_rewrite"])
@pytest.mark.parametrize("started_at", [0.0, 0.5, 91_000.25])
def test_the_first_piece_of_a_canvas_write_goes_out_at_once(name: str, started_at: float):
    """Whatever the clock reads: a machine that has just started counts from nearly nothing,
    and the card saying a document is on its way must not wait an interval for that."""
    preview = DraftPreview(Clock(started_at))
    assert preview.feed(piece('{"ti', name), 0) == shown('{"ti', name)


def test_an_event_says_which_call_it_belongs_to_and_which_attempt_wrote_it():
    preview = DraftPreview(Clock())
    event = preview.feed(piece('{"id"', "artifact_rewrite", index=3), 2)
    assert event == ToolCallDeltaEvent(index=3, name="artifact_rewrite", chunk='{"id"', attempt=2)


def test_pieces_that_follow_within_the_interval_are_held_back():
    clock = Clock()
    preview = DraftPreview(clock)
    assert preview.feed(piece("a"), 0) is not None
    for now in (0.0, 0.1, 1.5, 2.999):
        clock.now = now
        assert preview.feed(piece("b"), 0) is None


def test_a_piece_that_comes_an_interval_after_the_last_event_brings_out_all_that_was_held():
    clock = Clock()
    preview = DraftPreview(clock)
    preview.feed(piece('{"ti'), 0)
    clock.now = 1.0
    assert preview.feed(piece('tle": '), 0) is None
    clock.now = 2.999
    assert preview.feed(piece('"Kế '), 0) is None
    clock.now = 3.0
    assert preview.feed(piece('hoạch"'), 0) == shown('tle": "Kế hoạch"')


def test_the_interval_is_counted_from_the_last_event_not_from_the_first():
    """The second event resets the wait and takes what it sent out of the hold: the third
    carries only what came after it, and not before another whole interval has gone by."""
    clock = Clock()
    preview = DraftPreview(clock)
    preview.feed(piece("a"), 0)
    clock.now = 3.0
    assert preview.feed(piece("b"), 0) == shown("b")
    clock.now = 5.999
    assert preview.feed(piece("c"), 0) is None
    clock.now = 6.0
    assert preview.feed(piece("d"), 0) == shown("cd")


def test_a_long_document_is_previewed_once_per_interval_however_many_pieces_it_came_in():
    clock = Clock()
    preview = DraftPreview(clock)
    events = []
    for tick in range(101):  # ten seconds of a piece every tenth of a second
        clock.now = tick / 10
        events.append(preview.feed(piece("x"), 0))
    sent = {tick: event.chunk for tick, event in enumerate(events) if event is not None}
    assert sent == {0: "x", 30: "x" * 30, 60: "x" * 30, 90: "x" * 30}


def test_pieces_that_arrive_before_the_name_wait_for_it_and_then_go_out_with_it():
    clock = Clock(40.0)
    preview = DraftPreview(clock)
    assert preview.feed(piece('{"ti', name=""), 0) is None
    clock.now = 50.0  # no wait is long enough to send a piece of a call nobody has named
    assert preview.feed(piece("tle", name=""), 0) is None
    assert preview.emitted is False
    assert preview.feed(piece('": "A"'), 0) == shown('{"title": "A"')
    assert preview.emitted is True


@pytest.mark.parametrize("name", OTHER_TOOLS)
def test_a_call_of_any_other_tool_is_never_previewed(name: str):
    clock = Clock()
    preview = DraftPreview(clock)
    assert preview.feed(piece('{"path": "a.md", ', name), 0) is None
    clock.now = 10.0
    assert preview.feed(piece('"content": "bí mật"}', name), 0) is None
    assert preview.emitted is False


@pytest.mark.parametrize("name", OTHER_TOOLS)
def test_a_call_once_named_as_another_tool_stays_out_even_if_its_name_changes(name: str):
    """A stream may correct a name as it goes. What was written under the first name was
    never meant for the canvas, so the call is left alone for good rather than joined late."""
    clock = Clock()
    preview = DraftPreview(clock)
    assert preview.feed(piece('{"path": ', name), 0) is None
    clock.now = 10.0
    assert preview.feed(piece('"a.md"', "artifact_create"), 0) is None
    clock.now = 20.0
    assert preview.feed(piece("}", "artifact_create"), 0) is None
    assert preview.emitted is False


def test_pieces_held_for_a_name_are_let_go_when_the_name_is_another_tool():
    preview = DraftPreview(Clock())
    assert preview.feed(piece('{"command"', name=""), 0) is None
    assert preview.feed(piece(': "ls"', "shell_run"), 0) is None
    assert preview.feed(piece("}", "artifact_create"), 0) is None
    assert preview.emitted is False


def test_two_calls_in_one_answer_are_each_timed_and_gathered_on_their_own():
    clock = Clock()
    preview = DraftPreview(clock)
    assert preview.feed(piece("a0", index=0), 0) == shown("a0", index=0)
    clock.now = 1.0  # the second call's first piece does not wait for the first call's interval
    second = preview.feed(piece("b0", "artifact_rewrite", index=1), 0)
    assert second == shown("b0", "artifact_rewrite", index=1)
    clock.now = 2.0
    assert preview.feed(piece("a1", index=0), 0) is None
    assert preview.feed(piece("b1", "artifact_rewrite", index=1), 0) is None
    clock.now = 3.5  # an interval after the first call's event, not yet after the second's
    assert preview.feed(piece("b2", "artifact_rewrite", index=1), 0) is None
    assert preview.feed(piece("a2", index=0), 0) == shown("a1a2", index=0)
    clock.now = 4.0
    third = preview.feed(piece("b3", "artifact_rewrite", index=1), 0)
    assert third == shown("b1b2b3", "artifact_rewrite", index=1)


def test_another_tool_called_next_to_a_canvas_write_does_not_stop_its_preview():
    clock = Clock()
    preview = DraftPreview(clock)
    assert preview.feed(piece("{", "workspace_write", index=0), 0) is None
    assert preview.feed(piece("{", index=1), 0) == shown("{", index=1)
    clock.now = 3.0
    assert preview.feed(piece("x", "workspace_write", index=0), 0) is None
    assert preview.feed(piece('"title"', index=1), 0) == shown('"title"', index=1)


def test_it_says_whether_anything_went_out_since_it_was_last_reset():
    clock = Clock()
    preview = DraftPreview(clock)
    assert preview.emitted is False
    preview.feed(piece("a"), 0)
    assert preview.emitted is True
    clock.now = 1.0
    assert preview.feed(piece("b"), 0) is None  # a piece that is held does not unsay it
    assert preview.emitted is True
    assert preview.reset() is None
    assert preview.emitted is False


def test_what_is_still_held_when_an_attempt_ends_is_dropped_not_sent():
    """Nothing flushes the hold: the whole call arrives in the answer a moment later. After a
    reset the next attempt starts clean, so its first piece goes out at once and alone."""
    clock = Clock()
    preview = DraftPreview(clock)
    preview.feed(piece("first"), 0)
    clock.now = 1.0
    assert preview.feed(piece(" and the rest"), 0) is None
    preview.reset()
    clock.now = 1.5
    assert preview.feed(piece("again"), 1) == shown("again", attempt=1)


def test_a_reset_forgets_which_calls_were_left_alone():
    """The next attempt is a new answer: the call in a place that held another tool's call
    may now be a canvas write."""
    preview = DraftPreview(Clock())
    assert preview.feed(piece("{", "shell_run"), 0) is None
    preview.reset()
    assert preview.feed(piece("{"), 1) == shown("{", attempt=1)


def test_left_to_itself_it_reads_the_clock_that_only_goes_forward():
    """A wall clock set back in the middle of a document would stall the preview for as long
    as it was moved."""
    assert inspect.signature(DraftPreview).parameters["clock"].default is time.monotonic
