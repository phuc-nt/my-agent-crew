"""What rides along with a file `artifact_import` takes in. Only a code canvas is given a
language from the suffix. A title and a link to the original, sent with a file that replaces a
version, are recorded in that same write, which belongs to the conversation that imported it;
a link sent with a file that changes nothing still becomes the source. The write names the
version the file was compared with, so a save landing at the last moment is refused rather
than written over."""

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
from my_agent_crew.store.models import Conversation
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import ARTIFACT_VERSION_CONFLICT
from my_agent_crew.tools.artifact_context import CanvasAgent
from my_agent_crew.tools.artifact_file_texts import (
    IMPORT_REPLACED,
    IMPORT_SOURCE_READABLE,
    IMPORT_SOURCE_RECORDED,
)
from my_agent_crew.tools.artifact_texts import ARTIFACT_UNCHANGED
from my_agent_crew.tools.registry import ToolResult
from tests.canvas_helpers import PLAN, SWIM, call, created, persons_canvas, put, seen, tagged, turn

FILE = "notes/plan.md"
FROM_FILE = "# Kế hoạch\ntừ tệp\n"
SCRIPT = "print('xin chào')\n"
URL = "https://docs.example.com/plan?id=1"


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


async def test_only_a_code_canvas_takes_a_language_from_the_suffix(store: Store, root: Path):
    """A script asked for as markdown is markdown, with no language shown beside its kind."""
    put(root, "src/app.py", SCRIPT)
    turn(store)
    args = {"path": "src/app.py", "kind": "markdown"}
    result = await call(store, "artifact_import", args, root=root)
    summary = store.artifacts.get(tagged(result)[0])
    assert (summary.kind, summary.language) == ("markdown", "")
    assert f"(markdown, {len(SCRIPT.encode())} byte" in result.output


async def test_a_title_and_a_link_sent_with_a_file_are_recorded_in_the_write_that_replaces(
    store: Store, root: Path
):
    """One write, one version: the canvas is renamed and its source set as the file goes in."""
    conv = turn(store)
    art = await created(store, PLAN)
    result = await _import(store, root, art, title="Kế hoạch tuần", source_url=URL)
    summary, head = store.artifacts.get(art), store.artifacts.head(art)
    assert (summary.title, summary.source, summary.head_version) == ("Kế hoạch tuần", URL, 2)
    assert (head.content, head.note, head.conversation_id) == (FROM_FILE, IMPORT_NOTE, conv.id)
    payload = FROM_FILE.encode()
    done = IMPORT_REPLACED.format(
        path=FILE,
        title="Kế hoạch tuần",
        replaced=1,
        kind="markdown",
        size=len(payload),
        digest=hashlib.sha256(payload).hexdigest()[:12],
    )
    source = IMPORT_SOURCE_READABLE.format(source=URL)
    assert result.output.split("\n") == [artifact_tag(art, 2), done, source]


async def test_a_link_sent_with_a_file_that_changes_nothing_becomes_the_source(
    store: Store, root: Path
):
    """Told once: the same link sent again has nothing left to record."""
    conv = turn(store)
    art = persons_canvas(store, FROM_FILE, conv.id)
    first = await _import(store, root, art, source_url=URL)
    assert tagged(first) == (art, 1, True)
    recorded = IMPORT_SOURCE_RECORDED.format(source=URL)
    assert first.output.split("\n")[1:] == [ARTIFACT_UNCHANGED, recorded]
    assert store.artifacts.get(art).source == URL
    again = await _import(store, root, art, source_url=URL)
    assert again.output.split("\n")[1:] == [ARTIFACT_UNCHANGED]
    assert (store.artifacts.get(art).source, store.artifacts.get(art).head_version) == (URL, 1)


async def test_a_save_that_lands_as_the_file_is_written_is_refused_not_written_over(
    store: Store, root: Path, monkeypatch
):
    """Nothing waits between the look at the newest version and the write, so this is the last
    guard, for a writer on another thread: the write names the version it was compared with."""
    conv = turn(store)
    art = await created(store, PLAN)
    looked = CanvasAgent.seen

    def seen_while_the_person_saves(agent: CanvasAgent, asking: Conversation, canvas: str) -> int:
        store.artifacts.write(art, SWIM, USER, "")
        return looked(agent, asking, canvas)

    monkeypatch.setattr(CanvasAgent, "seen", seen_while_the_person_saves)
    result = await _import(store, root, art)
    assert result.output == TOOL_FAILED.format(error=ARTIFACT_VERSION_CONFLICT.format(head=2))
    summary, head = store.artifacts.get(art), store.artifacts.head(art)
    assert (summary.head_version, summary.source, head.content) == (2, "", SWIM)
    assert (seen(store, conv, art), canvas_writes(art)) == (1, 0)
