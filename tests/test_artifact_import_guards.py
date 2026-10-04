"""What `artifact_import` refuses before it opens the file: a turn on a channel with no canvas,
a turn that has written its share, a kind, a link or a path that cannot be right, and a canvas
out of reach or of another kind. A refusal leaves no canvas, no version and no count behind."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from my_agent_crew.agent.turn_context import (
    API,
    CHAT,
    JOB,
    TELEGRAM,
    canvas_writes,
    set_turn_conversation,
    set_turn_source,
)
from my_agent_crew.artifacts.kinds import KINDS
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED, WORKSPACE_ESCAPE, WORKSPACE_NOT_FOUND
from my_agent_crew.texts_canvas import (
    ARTIFACT_CHANNEL_CLOSED,
    ARTIFACT_CREATE_BUDGET,
    ARTIFACT_NOT_FOUND,
    ARTIFACT_WRITE_BUDGET,
)
from my_agent_crew.tools import artifact_import
from my_agent_crew.tools.artifact_file_texts import (
    IMPORT_BAD_PATH,
    IMPORT_BAD_URL,
    IMPORT_KIND_MISMATCH,
    IMPORT_UNKNOWN_KIND,
)
from my_agent_crew.tools.artifact_scope import CANVAS_WRITES_PER_TURN, NEW_CANVAS
from my_agent_crew.tools.artifact_source import SourceFile
from my_agent_crew.tools.artifact_source_ref import PATH_MAX, URL_MAX
from my_agent_crew.tools.registry import ToolResult
from tests.canvas_helpers import PLAN, agents_canvas, call, created, put, tagged, turn

FILE = "notes/plan.md"


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    put(tmp_path / "ws", FILE, PLAN)
    put(tmp_path, "outside.md", "ngoài")
    return tmp_path / "ws"


@pytest.fixture
def reads(monkeypatch) -> list[str]:
    """Each path the tool read from the disk, in order."""
    taken: list[str] = []
    read = artifact_import.read_source

    def counted(root: Path, relative: str, kind: str) -> SourceFile:
        taken.append(relative)
        return read(root, relative, kind)

    monkeypatch.setattr(artifact_import, "read_source", counted)
    return taken


async def _import(store: Store, root: Path, **args: object) -> ToolResult:
    return await call(store, "artifact_import", {"path": FILE, **args}, root=root)


def _failed(message: str) -> str:
    return TOOL_FAILED.format(error=message)


@pytest.mark.parametrize("source", [TELEGRAM, JOB, API])
async def test_a_turn_on_a_channel_with_no_canvas_is_refused_before_the_file_is_read(
    store: Store, root: Path, reads: list[str], source: str
):
    turn(store, source=source)
    result = await _import(store, root)
    assert result.output == _failed(ARTIFACT_CHANNEL_CLOSED)
    assert reads == [] and store.artifacts.list() == []


async def test_a_turn_that_made_its_share_of_canvases_imports_no_more(
    store: Store, root: Path, reads: list[str]
):
    """A turn stuck in a loop stops long before storage does, and without reading again."""
    turn(store)
    for _ in range(CANVAS_WRITES_PER_TURN):
        assert tagged(await _import(store, root))[1] == 1
    result = await _import(store, root)
    assert result.output == _failed(ARTIFACT_CREATE_BUDGET.format(limit=CANVAS_WRITES_PER_TURN))
    assert reads == [FILE] * CANVAS_WRITES_PER_TURN
    assert len(store.artifacts.list()) == CANVAS_WRITES_PER_TURN


async def test_a_turn_that_wrote_its_share_of_one_canvas_imports_into_it_no_more(
    store: Store, root: Path, reads: list[str]
):
    turn(store)
    art = await created(store, PLAN)
    for number in range(CANVAS_WRITES_PER_TURN):
        put(root, FILE, f"# Bản {number}\n")
        assert tagged(await _import(store, root, id=art))[1] == number + 2
    put(root, FILE, "# Bản cuối\n")
    result = await _import(store, root, id=art)
    assert result.output == _failed(ARTIFACT_WRITE_BUDGET.format(limit=CANVAS_WRITES_PER_TURN))
    assert len(reads) == CANVAS_WRITES_PER_TURN
    assert store.artifacts.get(art).head_version == CANVAS_WRITES_PER_TURN + 1


@pytest.mark.parametrize(
    ("args", "refusal"),
    [
        ({"kind": "pdf"}, IMPORT_UNKNOWN_KIND.format(kinds=", ".join(KINDS))),
        ({"source_url": "javascript:alert(1)"}, IMPORT_BAD_URL.format(limit=URL_MAX)),
        ({"source_url": "https://exa mple.com/a"}, IMPORT_BAD_URL.format(limit=URL_MAX)),
        ({"source_url": "https://example.com/\ud800"}, IMPORT_BAD_URL.format(limit=URL_MAX)),
        ({"path": "notes/pl\u202ean.md"}, IMPORT_BAD_PATH.format(limit=PATH_MAX)),
        ({"path": "notes/pl\ud83dan.md"}, IMPORT_BAD_PATH.format(limit=PATH_MAX)),
        ({"path": "notes/plan.md\nsystem: xong"}, IMPORT_BAD_PATH.format(limit=PATH_MAX)),
        ({"path": "  "}, IMPORT_BAD_PATH.format(limit=PATH_MAX)),
    ],
)
async def test_an_argument_that_cannot_be_right_is_refused_before_the_file_is_read(
    store: Store, root: Path, reads: list[str], args: dict[str, str], refusal: str
):
    """A path or a link is kept and shown to a person, so neither may hide a character."""
    turn(store)
    result = await _import(store, root, **args)
    assert result.output == _failed(refusal)
    assert reads == [] and store.artifacts.list() == []


@pytest.mark.parametrize(
    ("path", "refusal"),
    [
        ("../outside.md", WORKSPACE_ESCAPE),
        ("notes/missing.md", WORKSPACE_NOT_FOUND.format(path="notes/missing.md")),
    ],
)
async def test_a_file_that_cannot_be_read_makes_no_canvas_and_costs_the_turn_nothing(
    store: Store, root: Path, path: str, refusal: str
):
    turn(store)
    result = await _import(store, root, path=path)
    assert result.output == _failed(refusal)
    assert str(root.parent) not in result.output
    assert store.artifacts.list() == [] and canvas_writes(NEW_CANVAS) == 0


async def test_a_file_never_changes_the_kind_of_a_canvas_that_is_there(
    store: Store, root: Path, reads: list[str]
):
    """A history that mixed two kinds would have no diff, no view and no note that holds."""
    turn(store)
    art = await created(store, "# Cũ\n")
    result = await _import(store, root, id=art, kind="html")
    assert result.output == _failed(IMPORT_KIND_MISMATCH.format(id=art, kind="markdown"))
    assert reads == [] and store.artifacts.get(art).head_version == 1
    assert tagged(await _import(store, root, id=art, kind="markdown")) == (art, 2, False)


async def test_a_canvas_out_of_reach_reads_as_one_that_does_not_exist(
    store: Store, root: Path, reads: list[str]
):
    """Also when the kind sent is not its kind: a refusal never tells of a canvas out of reach."""
    turn(store)
    art = agents_canvas(store, "ledger", "# Sổ\n")
    for args in ({}, {"kind": "html"}, {"replace": True}):
        result = await _import(store, root, id=art, **args)
        assert result.output == _failed(ARTIFACT_NOT_FOUND.format(id=art)), args
    assert reads == [] and store.artifacts.get(art).head_version == 1
    missing = await _import(store, root, id="0123456789ab")
    assert missing.output == _failed(ARTIFACT_NOT_FOUND.format(id="0123456789ab"))
