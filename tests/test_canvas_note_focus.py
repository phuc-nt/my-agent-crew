"""What the canvas note says about the canvas open in the web chat: which canvas it is, once
per opening, and the passage the person selected in it, quoted once and placed by its lines
only when they hold it. Only a message from the web chat hears any of it."""

import pytest

from my_agent_crew.agent.turn_context import API, DELEGATE, JOB, TELEGRAM
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store
from my_agent_crew.texts_canvas import (
    CANVAS_NOTE_FOCUS,
    CANVAS_NOTE_NEW,
    CANVAS_NOTE_PICK,
    PICK_GONE,
    PICK_LINES,
    PICK_OLD,
    PICK_TEXT,
)
from tests.canvas_helpers import PLAN, SWIM, edited, framed, persons_canvas, say, seen_canvas

GOOD = {"version": 1, "text": "chạy 5 km", "line_start": 2, "line_end": 2}


def _open(art: str, version: int = 1, title: str = "Kế hoạch") -> str:
    return CANVAS_NOTE_FOCUS.format(title=title, id=art, version=version)


def _pick(version: int, text: str, start: int, end: int) -> dict:
    return {"version": version, "text": text, "line_start": start, "line_end": end}


def _picked(art: str, where: str, *quoted: str) -> list[str]:
    return [CANVAS_NOTE_PICK.format(title="Kế hoạch", id=art, where=where), *quoted]


def test_the_open_canvas_is_named_once_until_another_one_opens(store: Store):
    conv = store.create()
    art, other = seen_canvas(store, conv), seen_canvas(store, conv)
    store.artifact_links.set_focus(conv.id, art, None)
    assert say(store, conv) == framed(_open(art))
    assert say(store, conv) == ""
    store.artifact_links.set_focus(conv.id, art, None)
    assert say(store, conv) == ""
    store.artifact_links.set_focus(conv.id, other, None)
    assert say(store, conv) == framed(_open(other))
    store.artifact_links.set_focus(conv.id, art, None)
    assert say(store, conv) == framed(_open(art))


def test_a_selected_passage_is_quoted_once_and_then_cleared(store: Store):
    conv = store.create()
    art = seen_canvas(store, conv)
    store.artifact_links.set_focus(conv.id, art, GOOD)
    where = PICK_LINES.format(span="2", version=1)
    assert say(store, conv) == framed(*_picked(art, where, "> chạy 5 km"))
    focus = store.artifact_links.focus(conv.id)
    assert (focus.artifact_id, focus.selection, focus.noted) == (art, None, True)
    assert say(store, conv) == ""


@pytest.mark.parametrize(
    ("text", "start", "end", "where", "quoted"),
    [
        ("chạy 5 km\nbơi", 2, 3, PICK_LINES.format(span="2–3", version=1), ["chạy 5 km", "bơi"]),
        ("5 km", 2, 2, PICK_LINES.format(span="2", version=1), ["5 km"]),
        ("chạy 5 km", 3, 3, PICK_TEXT.format(version=1), ["chạy 5 km"]),
        ("chạy 5 km\nbơi", 2, 2, PICK_TEXT.format(version=1), ["chạy 5 km", "bơi"]),
    ],
)
def test_a_passage_is_placed_by_its_lines_only_when_those_lines_hold_it(
    store: Store, text: str, start: int, end: int, where: str, quoted: list[str]
):
    """Lines the browser counted wrong are not passed on: the agent is told to find the
    passage by its text instead."""
    conv = store.create()
    art = seen_canvas(store, conv)
    store.artifact_links.set_focus(conv.id, art, _pick(1, text, start, end))
    assert say(store, conv) == framed(*_picked(art, where, *[f"> {line}" for line in quoted]))


def test_a_passage_selected_on_an_older_version_says_which_version_is_newest(store: Store):
    conv = store.create()
    art = seen_canvas(store, conv)
    store.artifacts.write(art, PLAN + "ăn sáng\n", "agent:coach", "")
    store.artifact_links.mark_seen(conv.id, art, 2)
    store.artifact_links.set_focus(conv.id, art, GOOD)
    where = PICK_OLD.format(version=1, head=2)
    assert say(store, conv) == framed(*_picked(art, where, "> chạy 5 km"))


def test_a_passage_selected_on_a_folded_version_is_found_in_the_newest(store: Store, canvas_clock):
    conv = store.create()
    art = seen_canvas(store, conv)
    store.artifacts.write(art, SWIM, USER, "")
    canvas_clock.tick(10)
    store.artifacts.write(art, SWIM + "ăn sáng\n", USER, "")
    assert [v.version for v in store.artifacts.versions(art)] == [1, 3]
    store.artifact_links.mark_seen(conv.id, art, 3)
    store.artifact_links.set_focus(conv.id, art, _pick(2, "bơi 1 km", 3, 3))
    assert say(store, conv) == framed(*_picked(art, PICK_GONE.format(head=3), "> bơi 1 km"))


@pytest.mark.parametrize(
    "selection",
    [
        ["chạy 5 km"],
        {**GOOD, "version": True},
        {**GOOD, "version": 0},
        {**GOOD, "version": 5},
        {**GOOD, "version": "1"},
        {**GOOD, "text": ""},
        {**GOOD, "text": "   "},
        {**GOOD, "text": 5},
        {key: value for key, value in GOOD.items() if key != "line_start"},
        {**GOOD, "line_start": True},
        {**GOOD, "text": "chạy 10 km"},
    ],
)
def test_a_selection_that_cannot_be_quoted_only_names_the_open_canvas(store: Store, selection):
    """The web stores what the browser sent; a shape the note cannot trust, or text the
    version does not hold, is dropped rather than quoted."""
    conv = store.create()
    art = seen_canvas(store, conv)
    store.artifact_links.set_focus(conv.id, art, selection)
    assert say(store, conv) == framed(_open(art))
    focus = store.artifact_links.focus(conv.id)
    assert (focus.selection, focus.noted) == (None, True)


def test_a_selection_in_a_canvas_without_text_only_names_the_canvas(store: Store):
    conv = store.create()
    png = b"\x89PNG\r\n\x1a\n"
    art = store.artifacts.create("Ảnh", "image", "coach", "agent:coach", "", data=png).id
    store.artifact_links.mark_seen(conv.id, art, 1)
    store.artifact_links.set_focus(conv.id, art, GOOD)
    assert say(store, conv) == framed(_open(art, title="Ảnh"))
    assert store.artifact_links.focus(conv.id).selection is None


def test_an_open_canvas_the_agent_never_saw_is_named_and_announced(store: Store):
    conv = store.create()
    art = persons_canvas(store, PLAN, conv.id)
    store.artifact_links.set_focus(conv.id, art, None)
    title = "Ghi chú của người"
    new = CANVAS_NOTE_NEW.format(title=title, id=art, head=1)
    assert say(store, conv) == framed(_open(art, title=title), new)


@pytest.mark.parametrize("source", [TELEGRAM, API, JOB, f"{DELEGATE}:abc"])
def test_a_message_from_anywhere_but_the_web_chat_hears_nothing_of_the_open_canvas(
    store: Store, source: str
):
    """The person may have the canvas open on the web while writing from Telegram; that
    message still hears what changed, but neither the open canvas nor the selection, which
    wait for the web chat's next message."""
    conv = store.create()
    art = seen_canvas(store, conv)
    store.artifacts.write(art, SWIM, USER, "")
    store.artifact_links.set_focus(conv.id, art, GOOD)
    assert say(store, conv, source=source) == framed(*edited("Kế hoạch", art))
    focus = store.artifact_links.focus(conv.id)
    assert (focus.selection, focus.noted) == (GOOD, False)


def test_the_open_canvas_comes_first_and_the_rest_newest_first(store: Store, canvas_clock):
    conv = store.create()
    opened = seen_canvas(store, conv, "Kế hoạch 1")
    other = seen_canvas(store, conv, "Kế hoạch 2")
    canvas_clock.tick(1)
    store.artifacts.write(opened, SWIM, USER, "")
    canvas_clock.tick(1)
    store.artifacts.write(other, SWIM, USER, "")
    store.artifact_links.set_focus(conv.id, opened, None)
    assert say(store, conv) == framed(
        _open(opened, 2, "Kế hoạch 1"),
        *edited("Kế hoạch 1", opened),
        *edited("Kế hoạch 2", other),
    )
