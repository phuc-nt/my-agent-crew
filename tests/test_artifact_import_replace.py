"""`artifact_import` with an `id`: the file replaces the newest version of a canvas that is
there. A file that changes nothing adds no version; a file never goes over versions the
conversation has not seen unless `replace` says the person wants that, and even then those
versions stay unseen, so the next turn is still told of them."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from my_agent_crew.agent.turn_context import (
    CHAT,
    canvas_writes,
    set_turn_conversation,
    set_turn_source,
)
from my_agent_crew.artifacts.tag import artifact_tag
from my_agent_crew.store.artifact_models import IMPORT_NOTE, USER
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import ARTIFACT_AUTHORS
from my_agent_crew.tools import artifact_import
from my_agent_crew.tools.artifact_file_texts import (
    IMPORT_KEPT_IN_HISTORY,
    IMPORT_REPLACED,
    IMPORT_SOURCE_READABLE,
    IMPORT_SOURCE_RECORDED,
    IMPORT_WOULD_OVERWRITE,
    SOURCE_WORKSPACE,
)
from my_agent_crew.tools.artifact_source import SourceFile
from my_agent_crew.tools.artifact_texts import ARTIFACT_RENAMED, ARTIFACT_UNCHANGED
from my_agent_crew.tools.registry import ToolResult
from tests.canvas_helpers import (
    PLAN,
    PNG,
    SWIM,
    call,
    created,
    persons_canvas,
    put,
    say,
    seen,
    tagged,
    turn,
)

FILE = "notes/plan.md"
FROM_FILE = "# Kế hoạch\ntừ tệp\n"
SOURCE = SOURCE_WORKSPACE.format(path=FILE)
PERSONS = ARTIFACT_AUTHORS.format(groups="v2 người")


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    put(tmp_path / "ws", FILE, FROM_FILE)
    return tmp_path / "ws"


async def _import(store: Store, root: Path, art: str, **args: object) -> ToolResult:
    return await call(store, "artifact_import", {"path": FILE, "id": art, **args}, root=root)


def _replaced(art: str, version: int, *more: str) -> str:
    payload = FROM_FILE.encode()
    done = IMPORT_REPLACED.format(
        path=FILE,
        title="Kế hoạch",
        replaced=version - 1,
        kind="markdown",
        size=len(payload),
        digest=hashlib.sha256(payload).hexdigest()[:12],
    )
    return "\n".join([artifact_tag(art, version), done, *more])


async def test_a_file_replaces_the_newest_version_the_conversation_has_seen(
    store: Store, root: Path
):
    """The version is the agent's, marked as an import; a language sent with it changes none."""
    conv = turn(store)
    art = await created(store, PLAN)
    result = await _import(store, root, art, language="python")
    assert tagged(result) == (art, 2, False)
    summary, head = store.artifacts.get(art), store.artifacts.head(art)
    assert (head.content, head.author, head.note) == (FROM_FILE, "agent:coach", IMPORT_NOTE)
    assert (summary.kind, summary.language, summary.title) == ("markdown", "", "Kế hoạch")
    assert summary.source == "workspace:coach/notes/plan.md"
    assert (seen(store, conv, art), canvas_writes(art)) == (2, 1)
    assert result.output == _replaced(art, 2, IMPORT_SOURCE_READABLE.format(source=SOURCE))


async def test_a_file_that_changes_nothing_adds_no_version_and_opens_no_gate(
    store: Store, root: Path
):
    """Nothing is counted against the turn and nothing becomes seen: the agent has still not
    read the canvas. Where the file sits and a new title are recorded all the same."""
    conv = turn(store)
    art = persons_canvas(store, FROM_FILE, conv.id)
    first = await _import(store, root, art)
    assert tagged(first) == (art, 1, True)
    recorded = IMPORT_SOURCE_RECORDED.format(source=SOURCE)
    assert first.output.split("\n")[1:] == [ARTIFACT_UNCHANGED, recorded]
    assert store.artifacts.get(art).source == "workspace:coach/notes/plan.md"
    again = await _import(store, root, art, title="Kế hoạch tuần")
    renamed = ARTIFACT_RENAMED.format(title="Kế hoạch tuần")
    assert again.output.split("\n")[1:] == [ARTIFACT_UNCHANGED, renamed]
    args = {"path": FILE, "id": art}
    moved = await call(
        store, "artifact_import", args, root=root, agent_id="trainer", is_master=True
    )
    assert moved.output.split("\n")[1:] == [ARTIFACT_UNCHANGED, recorded]
    summary = store.artifacts.get(art)
    assert (summary.source, summary.title) == ("workspace:trainer/notes/plan.md", "Kế hoạch tuần")
    assert (summary.head_version, seen(store, conv, art), canvas_writes(art)) == (1, 0, 0)
    link = store.artifact_links.get(conv.id, art)
    assert link is not None and link.shared


async def test_a_picture_is_replaced_by_importing_it_again_and_only_when_its_bytes_differ(
    store: Store, root: Path
):
    turn(store)
    put(root, "logo.png", PNG)
    art, _, _ = tagged(await call(store, "artifact_import", {"path": "logo.png"}, root=root))
    same = await call(store, "artifact_import", {"path": "logo.png", "id": art}, root=root)
    assert tagged(same) == (art, 1, True)
    put(root, "logo.png", PNG + b"\x00")
    other = await call(store, "artifact_import", {"path": "logo.png", "id": art}, root=root)
    assert tagged(other) == (art, 2, False)
    assert store.artifacts.head(art).data == PNG + b"\x00"


async def test_a_file_does_not_go_over_versions_the_conversation_has_not_seen(
    store: Store, root: Path
):
    """The refusal says who wrote them, and nothing is written, counted or made seen."""
    conv = turn(store)
    art = await created(store, PLAN)
    store.artifacts.write(art, SWIM, USER, "")
    result = await _import(store, root, art)
    refusal = IMPORT_WOULD_OVERWRITE.format(id=art, head=2, authors=f" {PERSONS}")
    assert result.output == TOOL_FAILED.format(error=refusal)
    assert store.artifacts.head(art).content == SWIM
    assert (store.artifacts.get(art).source, seen(store, conv, art)) == ("", 1)
    assert canvas_writes(art) == 0
    unread = persons_canvas(store, PLAN, conv.id)
    assert not (await _import(store, root, unread, replace=False)).ok
    assert store.artifacts.get(unread).head_version == 1


async def test_replace_goes_over_unseen_versions_and_leaves_them_unseen(store: Store, root: Path):
    """The agent is told whose versions the file replaced, and the next turn's note still
    tells of them: writing over a version is not having read it."""
    conv = turn(store)
    art = await created(store, PLAN)
    store.artifacts.write(art, SWIM, USER, "")
    result = await _import(store, root, art, replace=True)
    assert tagged(result) == (art, 3, False)
    source = IMPORT_SOURCE_READABLE.format(source=SOURCE)
    assert result.output == _replaced(art, 3, PERSONS, IMPORT_KEPT_IN_HISTORY, source)
    assert store.artifacts.head(art).content == FROM_FILE
    assert store.artifacts.version(art, 2).content == SWIM
    assert seen(store, conv, art) == 1
    assert "v2 người" in say(store, conv)


async def test_a_change_made_while_the_file_was_read_is_not_written_over(
    store: Store, root: Path, monkeypatch
):
    """The newest version is looked up after the file is in hand, not before."""
    conv = turn(store)
    art = await created(store, PLAN)
    read = artifact_import.read_source

    def read_while_the_person_saves(root: Path, relative: str, kind: str) -> SourceFile:
        store.artifacts.write(art, SWIM, USER, "")
        return read(root, relative, kind)

    monkeypatch.setattr(artifact_import, "read_source", read_while_the_person_saves)
    result = await _import(store, root, art)
    refusal = IMPORT_WOULD_OVERWRITE.format(id=art, head=2, authors=f" {PERSONS}")
    assert result.output == TOOL_FAILED.format(error=refusal)
    assert (store.artifacts.head(art).content, seen(store, conv, art)) == (SWIM, 1)
