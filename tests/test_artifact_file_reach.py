"""Carrying a canvas to or from a file widens no one's reach. An export, and an import that
finds the file and the canvas alike, link the canvas to the conversation as a read does and
share it with no one, so what one turn of a delegation carried stays out of the next child's
reach. An import that writes a version shares the canvas, as any write does."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.store.db import Store
from my_agent_crew.store.models import Conversation
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import ARTIFACT_NOT_FOUND
from my_agent_crew.tools.artifact_scope import in_scope
from my_agent_crew.tools.registry import ToolResult
from tests.canvas_helpers import (
    PLAN,
    SWIM,
    agents_canvas,
    call,
    child_turn,
    persons_canvas,
    put,
    seen,
    tagged,
    turn,
)

FILE = "notes/plan.md"
CARRIES = ["artifact_export", "artifact_import"]


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    put(tmp_path / "ws", FILE, PLAN)
    return tmp_path / "ws"


async def _carry(store: Store, root: Path, tool: str, art: str, **who: object) -> ToolResult:
    """An export of `art` to a file, or an import of the file that holds what `art` holds."""
    path = "out/plan.md" if tool == "artifact_export" else FILE
    result = await call(store, tool, {"id": art, "path": path}, root=root, **who)
    assert result.ok, result.output
    assert store.artifacts.get(art).head_version == 1
    return result


def _shared(store: Store, conv: Conversation, art: str) -> bool | None:
    """Whether `conv` shares `art`, and None when the two are not linked at all."""
    link = store.artifact_links.get(conv.id, art)
    return None if link is None else link.shared


def _researcher_reaches(store: Store, conv: Conversation, art: str) -> bool:
    return in_scope(
        store,
        art,
        agent_id="researcher",
        is_master=False,
        conversation_id=conv.id,
        root_id=conv.root_id,
    )


async def _refused(store: Store, root: Path, art: str) -> None:
    """The researcher is told of no canvas, whichever way it asks, and gets no file."""
    asks = {
        "artifact_read": {"id": art},
        "artifact_export": {"id": art, "path": "theirs.md"},
        "artifact_import": {"id": art, "path": FILE},
    }
    for name, args in asks.items():
        result = await call(store, name, args, root=root, agent_id="researcher")
        assert result.output == TOOL_FAILED.format(error=ARTIFACT_NOT_FOUND.format(id=art)), name
    assert not (root / "theirs.md").exists()


@pytest.mark.parametrize("known", [False, True])
@pytest.mark.parametrize("tool", CARRIES)
async def test_what_a_child_carried_to_or_from_a_file_stays_out_of_the_next_childs_reach(
    store: Store, root: Path, tool: str, known: bool
):
    """The coach, delegated to, reaches a canvas of its own. Carrying it links it to the
    coach's conversation and leaves the root as it was, whether the root had it linked
    (`known`) or not, so the researcher delegated to next finds no canvas."""
    top = store.create()
    art = agents_canvas(store, "coach", PLAN)
    if known:
        store.artifact_links.link(top.id, art)
    child = child_turn(store, top)
    await _carry(store, root, tool, art)
    untouched = False if known else None
    assert (_shared(store, child, art), _shared(store, top, art)) == (False, untouched)
    assert seen(store, child, art) == 0
    sibling = child_turn(store, top)
    assert not _researcher_reaches(store, sibling, art)
    await _refused(store, root, art)


@pytest.mark.parametrize("tool", CARRIES)
async def test_what_the_master_carried_does_not_reach_its_delegated_child(
    store: Store, root: Path, tool: str
):
    """The master reaches a person's canvas that no link leads to. Carrying it links it to the
    master's conversation, as reading it would, and hands it to no child of that conversation."""
    top = turn(store)
    art = persons_canvas(store, PLAN)
    await _carry(store, root, tool, art, agent_id="master", is_master=True)
    assert _shared(store, top, art) is False
    child = child_turn(store, top)
    assert not _researcher_reaches(store, child, art)
    await _refused(store, root, art)


async def test_an_import_that_writes_a_version_shares_the_canvas_as_any_write_does(
    store: Store, root: Path
):
    """And carrying it afterwards takes nothing back: a link once shared stays shared."""
    top = store.create()
    art = agents_canvas(store, "coach", PLAN)
    child = child_turn(store, top)
    put(root, FILE, SWIM)
    args = {"id": art, "path": FILE, "replace": True}
    assert tagged(await call(store, "artifact_import", args, root=root)) == (art, 2, False)
    assert (_shared(store, child, art), _shared(store, top, art)) == (True, True)
    for tool in CARRIES:
        result = await call(store, tool, {"id": art, "path": FILE}, root=root)
        assert result.ok, (tool, result.output)
    assert (_shared(store, child, art), _shared(store, top, art)) == (True, True)
    sibling = child_turn(store, top)
    assert _researcher_reaches(store, sibling, art)
    read = await call(store, "artifact_read", {"id": art}, root=root, agent_id="researcher")
    assert read.ok, read.output
