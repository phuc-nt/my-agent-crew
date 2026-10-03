"""What an edit and a refused rewrite quote back of a change: a diff while the change is narrow
enough to compare line by line, drawn off the thread every conversation of the server shares,
and a sentence sending the agent to read the canvas when it spreads over too many lines. The
comparison is what grows with the square of those lines, so these tests watch for it being run
at all, not for how long it takes."""

from __future__ import annotations

import threading
from typing import Any

import pytest

from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.artifacts import diff
from my_agent_crew.artifacts.diff import MIDDLE_LINES
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import (
    ARTIFACT_AUTHORS,
    ARTIFACT_CONFLICT_WIDE,
    ARTIFACT_EDIT_DIFF_WIDE,
    ARTIFACT_VERSION_CONFLICT,
)
from my_agent_crew.tools import artifact_quote
from my_agent_crew.tools.artifact_texts import ARTIFACT_CONFLICT_DIFF
from tests.canvas_helpers import PLAN, SWIM, call, created, lines_text, tagged, turn

TODO_DONE = {"old": "TODO", "new": "XONG", "replace_all": True}


@pytest.fixture(autouse=True)
def fresh_turn():
    set_turn_source(CHAT)
    set_turn_conversation("")
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


@pytest.fixture
def no_comparison(monkeypatch):
    """Any line-by-line comparison of two texts fails the test that asked for none."""

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("the change was compared line by line")

    monkeypatch.setattr(diff, "SequenceMatcher", refuse)


def _spread(span: int) -> str:
    """A canvas with a TODO on its first line, another on line `span` and five lines after it:
    turning both into XONG leaves `span` lines between the ends the two versions share."""
    lines = lines_text(span + 5).split("\n")
    lines[0], lines[span - 1] = "TODO đầu", "TODO cuối"
    return "\n".join(lines)


def _drawn(span: int) -> str:
    """The diff of `_spread(span)` once both TODOs became XONG."""
    return (
        "```diff\n@@ dòng 1 @@\n- TODO đầu\n+ XONG đầu\n"
        f"@@ dòng {span} @@\n- TODO cuối\n+ XONG cuối\n```"
    )


async def test_an_edit_spread_over_too_many_lines_is_written_and_quotes_no_diff(
    store: Store, no_comparison
):
    turn(store)
    text = _spread(MIDDLE_LINES + 1)
    art = await created(store, text)
    result = await call(store, "artifact_edit", {"id": art, **TODO_DONE})
    assert tagged(result) == (art, 2, False)
    assert result.output.endswith(f"\n{ARTIFACT_EDIT_DIFF_WIDE}") and "```" not in result.output
    assert store.artifacts.head(art).content == text.replace("TODO", "XONG")


async def test_a_rewrite_refused_over_a_wide_change_sends_the_agent_to_read_instead(
    store: Store, no_comparison
):
    turn(store)
    text = _spread(MIDDLE_LINES + 1)
    art = await created(store, text)
    store.artifacts.write(art, text.replace("TODO", "XONG"), USER, "")
    result = await call(store, "artifact_rewrite", {"id": art, "content": "mới"})
    conflict = ARTIFACT_VERSION_CONFLICT.format(head=2)
    authors = ARTIFACT_AUTHORS.format(groups="v2 người")
    wide = ARTIFACT_CONFLICT_WIDE.format(seen=1, head=2)
    assert result.output == TOOL_FAILED.format(error=f"{conflict}\n{authors}\n{wide}")
    assert store.artifacts.head(art).version == 2


@pytest.mark.parametrize("tool", ["artifact_edit", "artifact_rewrite"])
async def test_a_change_just_inside_the_limit_is_still_compared_and_quoted(store: Store, tool: str):
    turn(store)
    text = _spread(MIDDLE_LINES)
    art = await created(store, text)
    if tool == "artifact_edit":
        result = await call(store, tool, {"id": art, **TODO_DONE})
        assert tagged(result) == (art, 2, False)
        assert result.output.endswith(f"\n{_drawn(MIDDLE_LINES)}")
    else:
        store.artifacts.write(art, text.replace("TODO", "XONG"), USER, "")
        result = await call(store, tool, {"id": art, "content": "mới"})
        heading = ARTIFACT_CONFLICT_DIFF.format(seen=1, head=2)
        assert not result.ok
        assert result.output.endswith(f"\n{heading}\n{_drawn(MIDDLE_LINES)}")


@pytest.mark.parametrize("tool", ["artifact_edit", "artifact_rewrite"])
async def test_a_diff_is_drawn_off_the_thread_that_serves_every_conversation(
    store: Store, monkeypatch, tool: str
):
    drawn_on: list[int] = []
    real = artifact_quote.fenced_diff

    def draw(*args: Any) -> str:
        drawn_on.append(threading.get_ident())
        return real(*args)

    monkeypatch.setattr(artifact_quote, "fenced_diff", draw)
    turn(store)
    art = await created(store, PLAN)
    if tool == "artifact_edit":
        args = {"id": art, "old": "bơi", "new": "bơi 1 km"}
    else:
        store.artifacts.write(art, SWIM, USER, "")
        args = {"id": art, "content": "mới"}
    await call(store, tool, args)
    assert len(drawn_on) == 1 and drawn_on[0] != threading.get_ident()
