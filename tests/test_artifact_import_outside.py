"""A path that leaves the workspace is told so by `artifact_import` before anything else about
it is looked at: not its suffix, not the kind sent with it, not the canvas it was to go into.
Nothing is opened to tell, and a link a person put inside the workspace is followed as before."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from my_agent_crew.agent.turn_context import (
    CHAT,
    canvas_writes,
    set_turn_conversation,
    set_turn_source,
)
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED, WORKSPACE_ESCAPE
from my_agent_crew.tools import artifact_import, artifact_source
from my_agent_crew.tools.artifact_scope import NEW_CANVAS
from my_agent_crew.tools.registry import ToolResult
from tests.canvas_helpers import PLAN, agents_canvas, call, created, put, tagged, turn

REFUSED = TOOL_FAILED.format(error=WORKSPACE_ESCAPE)
# No suffix, a suffix no kind stands for, one a kind does stand for, and a home that is no one's.
OUTSIDE = ["../../etc/hosts", "../outside.xyz", "../outside.md", "/etc/hosts", "~no-such-user-0/a"]


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    put(tmp_path / "ws", "notes/plan.md", PLAN)
    for name in ("outside.md", "outside.xyz"):
        put(tmp_path, name, "ngoài")
    return tmp_path / "ws"


@pytest.fixture
def opened(monkeypatch) -> list[str]:
    """Each path the tool went to read, and each file it opened to do so."""
    taken: list[str] = []
    read, open_file = artifact_import.read_source, artifact_source.os.open

    def counted(root: Path, relative: str, kind: str) -> object:
        taken.append(relative)
        return read(root, relative, kind)

    def watched(path: object, *args: object, **kwargs: object) -> int:
        taken.append(str(path))
        return open_file(path, *args, **kwargs)

    monkeypatch.setattr(artifact_import, "read_source", counted)
    monkeypatch.setattr(artifact_source.os, "open", watched)
    return taken


async def _import(store: Store, root: Path, **args: object) -> ToolResult:
    return await call(store, "artifact_import", args, root=root)


@pytest.mark.parametrize("path", OUTSIDE)
@pytest.mark.parametrize(
    "args", [{}, {"kind": "markdown"}, {"kind": "code"}, {"kind": "bảng tính"}, {"title": "Máy"}]
)
async def test_a_path_out_of_the_workspace_is_told_so_whatever_its_suffix_or_kind(
    store: Store, root: Path, opened: list[str], path: str, args: dict[str, str]
):
    """The model is told what is wrong with the path, not sent to look for another suffix, nor
    for another kind when the one it sent is no kind of canvas at all."""
    turn(store)
    result = await _import(store, root, path=path, **args)
    assert not result.ok and result.output == REFUSED
    assert opened == [] and store.artifacts.list() == [] and canvas_writes(NEW_CANVAS) == 0


@pytest.mark.parametrize("path", OUTSIDE)
async def test_a_path_out_of_the_workspace_is_told_so_before_the_canvas_it_was_to_go_into(
    store: Store, root: Path, opened: list[str], path: str
):
    """Also when the kind sent is not the canvas's own, and when the canvas is out of reach:
    the path is wrong whichever canvas was meant."""
    turn(store)
    mine, theirs = await created(store, "# Cũ\n"), agents_canvas(store, "ledger", "# Sổ\n")
    for art in (mine, theirs, "0123456789ab"):
        for args in ({}, {"kind": "html"}, {"kind": "markdown"}, {"replace": True}):
            result = await _import(store, root, path=path, id=art, **args)
            assert not result.ok and result.output == REFUSED, (art, args)
    # Nothing opened, and the turn charged for the one canvas it made and for no write into it.
    assert opened == [] and (canvas_writes(NEW_CANVAS), canvas_writes(mine)) == (1, 0)
    assert [store.artifacts.get(art).head_version for art in (mine, theirs)] == [1, 1]


async def test_a_link_inside_the_workspace_is_still_followed_to_where_it_leads(
    store: Store, root: Path, opened: list[str]
):
    """The same rule `workspace_read` keeps: the path as written stays inside, so it is read."""
    (root / "linked.md").symlink_to(root.parent / "outside.md")
    turn(store)
    art, version, _ = tagged(await _import(store, root, path="linked.md"))
    assert version == 1 and store.artifacts.head(art).content == "ngoài"
    assert opened == ["linked.md", str(root.resolve() / "linked.md")]


async def test_an_absolute_path_that_lands_inside_the_workspace_is_read(
    store: Store, root: Path, opened: list[str]
):
    turn(store)
    inside = str(root / "notes" / "plan.md")
    art, _, _ = tagged(await _import(store, root, path=inside))
    assert store.artifacts.head(art).content == PLAN and opened[0] == inside
