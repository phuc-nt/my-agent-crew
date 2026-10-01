"""The canvas note a person's message is stored with: what changed in the conversation's
canvases since the agent last heard, shown as a diff only when the person alone wrote it,
told once, and moving what the conversation has seen only when the diff showed all of it."""

import logging
import sqlite3

import pytest

from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.artifacts.diff import render_diff
from my_agent_crew.store import canvas_note
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.canvas_note import DIFF_CHARS, NOTE_CHARS, Note, build_note
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import (
    ARTIFACT_AUTHORS,
    ARTIFACT_REWRITE_UNSEEN,
    ARTIFACT_VERSION_CONFLICT,
    CANVAS_NOTE_BUMP,
    CANVAS_NOTE_CLOSE,
    CANVAS_NOTE_EDITED,
    CANVAS_NOTE_LARGE,
    CANVAS_NOTE_MORE,
    CANVAS_NOTE_NEW,
    CANVAS_NOTE_OPEN,
    CANVAS_NOTE_READ,
)
from tests.canvas_helpers import (
    PLAN,
    SWIM,
    call,
    created,
    edited,
    framed,
    lines_text,
    noted,
    persons_canvas,
    say,
    seen,
    tagged,
    turn,
)

LEDGER = PLAN + "ăn sáng\n"
CUT = PLAN.replace("bơi", "bơi " + "x" * 400)


@pytest.fixture(autouse=True)
def fresh_turn():
    set_turn_source(CHAT)
    set_turn_conversation("")
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


def _failed(message: str) -> str:
    return TOOL_FAILED.format(error=message)


async def _rewrite(store: Store, art: str):
    return await call(store, "artifact_rewrite", {"id": art, "content": "# Kế hoạch\nnghỉ\n"})


def _bump(title: str, art: str, head: int, groups: str | None = None) -> str:
    """The one line a note gives a canvas it does not diff."""
    parts = [CANVAS_NOTE_BUMP.format(title=title, id=art, head=head)]
    if groups is not None:
        parts.append(ARTIFACT_AUTHORS.format(groups=groups))
    return " ".join([*parts, CANVAS_NOTE_READ])


def test_a_conversation_without_canvases_stores_no_note(store: Store):
    conv = turn(store)
    assert say(store, conv) == ""
    assert build_note(store, conv.id, CHAT) == Note()


async def test_a_canvas_the_agent_never_saw_is_named_once_and_still_cannot_be_rewritten(
    store: Store,
):
    """With nothing seen there is nothing to diff from: the note names the canvas, and the
    conversation must still read it whole before rewriting it."""
    conv = turn(store)
    art = persons_canvas(store, PLAN, conv.id)
    new = CANVAS_NOTE_NEW.format(title="Ghi chú của người", id=art, head=1)
    assert say(store, conv) == framed(new)
    assert (seen(store, conv, art), noted(store, conv, art)) == (0, 1)
    assert say(store, conv) == ""
    assert (await _rewrite(store, art)).output == _failed(ARTIFACT_REWRITE_UNSEEN.format(id=art))


async def test_a_persons_edit_is_shown_as_a_diff_that_makes_the_new_version_seen(store: Store):
    conv = turn(store)
    art = await created(store, PLAN)
    store.artifacts.write(art, PLAN.replace("chạy 5 km", "chạy 8 km"), USER, "")
    heading = CANVAS_NOTE_EDITED.format(title="Kế hoạch", id=art, base=1, head=2)
    assert say(store, conv) == framed(heading, "@@ dòng 2 @@", "- chạy 5 km", "+ chạy 8 km")
    assert (seen(store, conv, art), noted(store, conv, art)) == (2, 2)
    assert tagged(await _rewrite(store, art))[1] == 3
    assert say(store, conv) == ""


def _by_ledger(store: Store, art: str) -> list[str]:
    store.artifacts.write(art, LEDGER, "agent:ledger", "")
    return [_bump("Kế hoạch", art, 2, "v2 agent:ledger")]


def _cut_line(store: Store, art: str) -> list[str]:
    store.artifacts.write(art, CUT, USER, "")
    heading = CANVAS_NOTE_EDITED.format(title="Kế hoạch", id=art, base=1, head=2)
    return [heading, *render_diff(PLAN, CUT, DIFF_CHARS).split("\n"), CANVAS_NOTE_READ]


def _restored(store: Store, art: str) -> list[str]:
    store.artifacts.restore(art, 1, USER, "")
    return [_bump("Kế hoạch", art, 2, "v2 người khôi phục v1")]


@pytest.mark.parametrize("change", [_by_ledger, _cut_line, _restored])
async def test_a_note_that_does_not_show_every_change_in_full_leaves_the_rewrite_refused(
    store: Store, change
):
    """Another agent's text, a cut line and a restore are told without making the version
    seen, so a rewrite still cannot write over what the agent never saw."""
    conv = turn(store)
    art = await created(store, PLAN)
    lines = change(store, art)
    assert say(store, conv) == framed(*lines)
    assert (seen(store, conv, art), noted(store, conv, art)) == (1, 2)
    output = (await _rewrite(store, art)).output
    assert output.startswith(_failed(ARTIFACT_VERSION_CONFLICT.format(head=2) + "\n"))
    assert say(store, conv) == ""


async def test_a_persons_edit_after_a_told_change_is_diffed_from_what_was_told(store: Store):
    """The note diffs from the newest version it told, so the agent hears each change once,
    but `seen` stays where the agent last saw the canvas whole."""
    conv = turn(store)
    art = await created(store, PLAN)
    store.artifacts.write(art, LEDGER, "agent:ledger", "")
    say(store, conv)
    store.artifacts.write(art, SWIM + "ăn sáng\n", USER, "")
    assert say(store, conv) == framed(*edited("Kế hoạch", art, 2, 3), CANVAS_NOTE_READ)
    assert (seen(store, conv, art), noted(store, conv, art)) == (1, 3)
    output = (await _rewrite(store, art)).output
    assert output.startswith(_failed(ARTIFACT_VERSION_CONFLICT.format(head=3) + "\n"))


async def test_a_told_version_is_kept_from_the_persons_next_autosave(store: Store, canvas_clock):
    """An autosave would fold into the version just told; it must stay, or the next note
    would have nothing to diff from."""
    conv = turn(store)
    art = persons_canvas(store, PLAN, conv.id)
    say(store, conv)
    canvas_clock.tick(10)
    store.artifacts.write(art, SWIM, USER, "")
    assert [v.version for v in store.artifacts.versions(art)] == [1, 2]
    title = "Ghi chú của người"
    assert say(store, conv) == framed(*edited(title, art), CANVAS_NOTE_READ)
    assert (seen(store, conv, art), noted(store, conv, art)) == (0, 2)


async def test_an_edit_the_person_undid_tells_nothing_and_makes_the_canvas_seen(
    store: Store, canvas_clock
):
    conv = turn(store)
    art = await created(store, PLAN)
    store.artifacts.write(art, SWIM, USER, "")
    canvas_clock.tick(10)
    store.artifacts.write(art, PLAN, USER, "")
    assert [v.version for v in store.artifacts.versions(art)] == [1, 3]
    assert say(store, conv) == ""
    assert (seen(store, conv, art), noted(store, conv, art)) == (3, 3)


@pytest.mark.parametrize("changed", [3, 4])
async def test_a_change_past_the_middle_limit_is_told_in_one_line(
    store: Store, monkeypatch, changed: int
):
    monkeypatch.setattr(canvas_note, "MIDDLE_LINES", 3)
    conv = turn(store)
    before = lines_text(10)
    lines = before.split("\n")
    lines[2 : 2 + changed] = [line.upper() for line in lines[2 : 2 + changed]]
    after = "\n".join(lines)
    art = await created(store, before)
    store.artifacts.write(art, after, USER, "")
    if changed == 3:
        heading = CANVAS_NOTE_EDITED.format(title="Kế hoạch", id=art, base=1, head=2)
        assert say(store, conv) == framed(
            heading, *render_diff(before, after, DIFF_CHARS).split("\n")
        )
        assert seen(store, conv, art) == 2
    else:
        large = CANVAS_NOTE_LARGE.format(title="Kế hoạch", id=art, base=1, head=2)
        assert say(store, conv) == framed(f"{large} {CANVAS_NOTE_READ}")
        assert (seen(store, conv, art), noted(store, conv, art)) == (1, 2)


async def _edited_canvases(store: Store, canvas_clock, count: int = 4) -> list[str]:
    """`count` canvases the agent made, each then edited by the person, newest edit last."""
    arts = [await created(store, PLAN, f"Kế hoạch {n}") for n in range(1, count + 1)]
    for art in arts:
        canvas_clock.tick(1)
        store.artifacts.write(art, SWIM, USER, "")
    return arts


async def test_a_note_diffs_three_canvases_at_most_newest_first(store: Store, canvas_clock):
    conv = turn(store)
    arts = await _edited_canvases(store, canvas_clock)
    assert say(store, conv) == framed(
        *edited("Kế hoạch 4", arts[3]),
        *edited("Kế hoạch 3", arts[2]),
        *edited("Kế hoạch 2", arts[1]),
        _bump("Kế hoạch 1", arts[0], 2, "v2 người"),
    )
    assert [seen(store, conv, art) for art in arts] == [1, 2, 2, 2]
    assert [noted(store, conv, art) for art in arts] == [2, 2, 2, 2]


async def test_canvases_that_do_not_fit_are_counted_and_told_in_the_next_note(
    store: Store, canvas_clock, monkeypatch
):
    conv = turn(store)
    arts = await _edited_canvases(store, canvas_clock, 3)
    expected = framed(*edited("Kế hoạch 3", arts[2]), CANVAS_NOTE_MORE.format(n=2))
    monkeypatch.setattr(canvas_note, "NOTE_CHARS", len(expected))
    assert say(store, conv) == expected
    assert [noted(store, conv, art) for art in arts] == [0, 0, 2]
    assert [seen(store, conv, art) for art in arts] == [1, 1, 2]
    monkeypatch.setattr(canvas_note, "NOTE_CHARS", NOTE_CHARS)
    assert say(store, conv) == framed(
        *edited("Kế hoạch 2", arts[1]), *edited("Kế hoạch 1", arts[0])
    )


async def test_a_note_never_outgrows_its_ceiling_and_counts_what_it_left_out(
    store: Store, canvas_clock
):
    conv = turn(store)
    text = lines_text(60, 60)
    arts = []
    for n in range(16):
        title = f"Kế hoạch số {n:02d} " + "rất dài " * 7
        arts.append(await created(store, text, title))
    for art in arts:
        canvas_clock.tick(1)
        store.artifacts.write(art, text.upper(), USER, "")
    note = say(store, conv)
    lines = note.split("\n")
    shown = [art for art in arts if art in note]
    assert len(note) <= NOTE_CHARS
    assert (lines[0], lines[-1]) == (CANVAS_NOTE_OPEN, CANVAS_NOTE_CLOSE)
    assert len(shown) < len(arts)
    assert lines[-2] == CANVAS_NOTE_MORE.format(n=len(arts) - len(shown))
    assert [noted(store, conv, art) for art in arts] == [2 if art in shown else 0 for art in arts]
    assert [seen(store, conv, art) for art in arts] == [1] * len(arts)


async def test_a_canvas_that_fails_to_build_is_told_in_one_line_and_the_rest_still_show(
    store: Store, canvas_clock, monkeypatch, caplog
):
    conv = turn(store)
    broken, fine = await _edited_canvases(store, canvas_clock, 2)
    versions = store.artifacts.versions

    def failing(artifact_id: str):
        if artifact_id == broken:
            raise sqlite3.OperationalError("hỏng")
        return versions(artifact_id)

    monkeypatch.setattr(store.artifacts, "versions", failing)
    with caplog.at_level(logging.ERROR):
        note = say(store, conv)
    assert note == framed(*edited("Kế hoạch 2", fine), _bump("Kế hoạch 1", broken, 2))
    assert (seen(store, conv, broken), noted(store, conv, broken)) == (1, 2)
    assert any(record.levelno == logging.ERROR for record in caplog.records)


async def test_building_a_note_writes_nothing(store: Store):
    """The note only reads; the marks it hands back run inside the message's transaction."""
    conv = turn(store)
    art = await created(store, PLAN)
    store.artifacts.write(art, SWIM, USER, "")
    other = persons_canvas(store, PLAN, conv.id)
    selection = {"version": 1, "text": "bơi", "line_start": 3, "line_end": 3}
    store.artifact_links.set_focus(conv.id, other, selection)
    changes = store._conn.total_changes
    note = build_note(store, conv.id, CHAT)
    assert note.text.startswith(CANVAS_NOTE_OPEN) and note.marks
    assert store._conn.total_changes == changes
    assert store._conn.in_transaction is False
    assert (seen(store, conv, art), noted(store, conv, art)) == (1, 0)
    focus = store.artifact_links.focus(conv.id)
    assert (focus.selection, focus.noted) == (selection, False)
