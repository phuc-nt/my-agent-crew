"""Whether what the person did on a canvas reached the agent: the note of the message after the
steps tells of every canvas the person made or saved, at the version they left it, in any form a
note tells a change in, and quotes the passage the message carried as the note quotes it."""

from __future__ import annotations

import pytest
from eval_canvas import NoteDue
from eval_check import RUN, Failure
from eval_note import note_failures

from my_agent_crew.store.canvas_quote import PICK_CHARS, quoted, shown
from my_agent_crew.texts import LOOP_REDIRECT
from my_agent_crew.texts_canvas import (
    CANVAS_NOTE_BUMP,
    CANVAS_NOTE_CLOSE,
    CANVAS_NOTE_EDITED,
    CANVAS_NOTE_FOCUS,
    CANVAS_NOTE_LARGE,
    CANVAS_NOTE_NEW,
    CANVAS_NOTE_OPEN,
    CANVAS_NOTE_PICK,
    CANVAS_NOTE_READ,
    PICK_LINES,
)

TITLE = "Việc cuối tuần"
FOCUS = CANVAS_NOTE_FOCUS.format(title=TITLE, id="a1", version=3)
PICKED = CANVAS_NOTE_PICK.format(title=TITLE, id="a1", where=PICK_LINES.format(span="3", version=3))


def note(*lines: str) -> str:
    return "\n".join([CANVAS_NOTE_OPEN, *lines, CANVAS_NOTE_CLOSE])


def told(text: str, context: str | None = None) -> dict:
    return {"role": "user", "content": text, "context": context}


def said(text: str) -> dict:
    return {"role": "assistant", "content": text, "tool_calls": []}


def details(messages: list[dict], sent: list[str], due: list[NoteDue]) -> list[str]:
    failures = list(note_failures(messages, sent, due))
    assert all(f.assertion == RUN for f in failures)
    return [f.detail for f in failures]


@pytest.mark.parametrize(
    "told_of",
    [
        CANVAS_NOTE_NEW.format(title=TITLE, id="a1", head=3),
        CANVAS_NOTE_EDITED.format(title=TITLE, id="a1", base=1, head=3)
        + "\n@@ dòng 3 @@\n- - Giặt rèm\n+ - Giặt chăn",
        f"{CANVAS_NOTE_BUMP.format(title=TITLE, id='a1', head=3)} {CANVAS_NOTE_READ}",
        f"{CANVAS_NOTE_LARGE.format(title=TITLE, id='a1', base=2, head=3)} {CANVAS_NOTE_READ}",
    ],
    ids=["new", "edited", "bump", "large"],
)
def test_a_note_telling_of_the_canvas_at_the_version_the_person_left_passes(told_of):
    messages = [told("hi"), said("hello"), told("look", note(FOCUS, told_of)), said("seen")]

    assert details(messages, ["hi", "look"], [NoteDue(), NoteDue({"a1": 3})]) == []


@pytest.mark.parametrize(
    "context", [None, "", note(FOCUS)], ids=["no-note", "empty-note", "the-open-canvas-only"]
)
def test_a_message_whose_note_does_not_tell_of_the_change_fails_the_run(context):
    failures = list(note_failures([told("look", context)], ["look"], [NoteDue({"a1": 3})]))

    assert failures == [Failure(RUN, "the canvas note of message 1 does not tell of a1 at v3")]


def test_a_note_of_an_older_version_another_canvas_or_the_selection_does_not_count():
    older = CANVAS_NOTE_EDITED.format(title=TITLE, id="a1", base=1, head=2)
    other = CANVAS_NOTE_NEW.format(title=TITLE, id="a12", head=3)
    later = CANVAS_NOTE_NEW.format(title=TITLE, id="a1", head=30)
    messages = [told("look", note(older, other, later, PICKED, "> - Giặt chăn"))]

    assert details(messages, ["look"], [NoteDue({"a1": 3})]) == [
        "the canvas note of message 1 does not tell of a1 at v3"
    ]


def test_a_quoted_line_that_reads_like_a_change_does_not_count():
    quote = "> " + CANVAS_NOTE_BUMP.format(title=TITLE, id="a1", head=3)
    messages = [told("look", note(PICKED, quote))]

    assert details(messages, ["look"], [NoteDue({"a1": 3})]) == [
        "the canvas note of message 1 does not tell of a1 at v3"
    ]


def test_every_canvas_the_person_made_or_saved_is_told_of_on_its_own():
    first = CANVAS_NOTE_NEW.format(title="Thực đơn", id="a2", head=1)
    messages = [told("look", note(first))]

    assert details(messages, ["look"], [NoteDue({"a1": 3, "a2": 1})]) == [
        "the canvas note of message 1 does not tell of a1 at v3"
    ]


def test_the_passage_a_message_carried_is_quoted_as_the_note_quotes_it():
    # A line break pasted from a word processor is shown escaped, as the note shows it.
    passage = "Thân gửi cả lớp,\u2028Các bạn nhớ nhé:\n\nHọp lớp vào thứ Bảy 31/2."
    assert shown(passage) != passage
    due = [NoteDue(passage=passage)]

    as_the_note_quotes_it = note(PICKED, quoted(shown(passage)))
    assert details([told("sửa giúp", as_the_note_quotes_it)], ["sửa giúp"], due) == []
    cut_short = note(PICKED, "> Thân gửi cả lớp,")
    assert details([told("sửa giúp", cut_short)], ["sửa giúp"], due) == [
        "the canvas note of message 1 does not quote the passage it carried"
    ]


def test_a_passage_longer_than_the_note_quotes_passes_with_the_part_it_quotes():
    passage = "\n".join(f"- Dòng {n}: việc cần làm trong tuần này" for n in range(60))
    assert len(passage) > PICK_CHARS

    messages = [told("xem", note(PICKED, quoted(passage)))]

    assert details(messages, ["xem"], [NoteDue({}, passage)]) == []


def test_each_note_is_read_from_the_message_holding_the_text_sent_not_a_note_the_server_wrote():
    made = CANVAS_NOTE_NEW.format(title=TITLE, id="a1", head=1)
    edited = CANVAS_NOTE_EDITED.format(title=TITLE, id="a1", base=1, head=2)
    messages = [
        told("tạo đi", note(made)),
        said("look"),  # the agent saying the next text first does not hold it
        told(LOOP_REDIRECT.format(names="artifact_edit", count=3)),
        told("look", note(edited, "@@ dòng 2 @@", "+ - Giặt chăn")),
        said("Đã xem."),
    ]
    due = [NoteDue({"a1": 1}), NoteDue({"a1": 2})]

    assert details(messages, ["tạo đi", "look"], due) == []


def test_a_text_the_conversation_does_not_hold_is_left_for_observe_to_report():
    messages = [told("one", note(CANVAS_NOTE_NEW.format(title=TITLE, id="a1", head=1)))]
    due = [NoteDue({"a1": 1}), NoteDue({"a1": 2}, "Giặt chăn")]

    assert details(messages, ["one", "two"], due) == []
