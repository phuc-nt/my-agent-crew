"""Which canvases an agent wrote in a conversation: what a delegation hands back to the agent
that asked for it. A version counts when an agent wrote it in that conversation, whether it
began the canvas, changed one that was there or took it from a file. What a person saved does
not count, and neither does anything that adds no version."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.agents.profile import DEFAULT_AGENT_ID
from my_agent_crew.server import create_app
from my_agent_crew.store.artifact_models import IMPORT_NOTE, USER
from my_agent_crew.store.artifact_usage import Written
from my_agent_crew.store.db import Store
from my_agent_crew.store.models import Conversation
from tests.canvas_helpers import (
    PLAN,
    SWIM,
    agents_canvas,
    call,
    child_turn,
    persons_canvas,
    put,
    tagged,
)

COACH = "agent:coach"
FILE = "notes/plan.md"


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A workspace whose FILE holds PLAN."""
    put(tmp_path / "ws", FILE, PLAN)
    return tmp_path / "ws"


def _began(store: Store, conv: Conversation, title: str = "Kế hoạch") -> str:
    """A canvas the coach began in `conv`."""
    return store.artifacts.create(title, "markdown", "coach", COACH, conv.id, PLAN).id


def test_a_canvas_the_agent_began_and_one_it_only_changed_are_both_listed(store: Store):
    """Each at the newest version the agent wrote there, under the title it has now. The one
    written first comes first, though the other canvas is the older of the two."""
    top = store.create()
    child = store.create(root_id=top.id)
    given = persons_canvas(store, PLAN, top.id)
    began = _began(store, child)
    store.artifacts.write(given, SWIM, COACH, child.id)
    store.artifacts.write(began, SWIM, COACH, child.id, title="Kế hoạch tuần")
    assert store.artifacts.written_in(child.id) == [
        Written(began, 2, "Kế hoạch tuần"),
        Written(given, 2, "Ghi chú của người"),
    ]
    assert store.artifacts.written_in(top.id) == []


def test_each_conversation_lists_what_was_written_in_it_alone(store: Store):
    """A canvas written in two conversations is in both, at the version each one reached,
    which is not the newest version of the canvas when the other conversation wrote later."""
    first, second = store.create(), store.create()
    art = _began(store, first)
    store.artifacts.write(art, SWIM, "agent:researcher", second.id)
    other = _began(store, second, "Khác")
    store.artifacts.write(art, PLAN, COACH, first.id)
    assert store.artifacts.written_in(first.id) == [Written(art, 3, "Kế hoạch")]
    assert store.artifacts.written_in(second.id) == [
        Written(art, 2, "Kế hoạch"),
        Written(other, 1, "Khác"),
    ]
    assert store.artifacts.written_in(store.create().id) == []


def test_what_a_person_saved_in_the_conversation_is_not_the_agents_writing(store: Store):
    """A person may open the delegated conversation and edit there. Their canvas is left
    out, and on one the agent wrote the version named stays the agent's newest, not the
    newest there is."""
    child = store.create()
    art, theirs = _began(store, child), persons_canvas(store, PLAN)
    for canvas in (art, theirs):
        store.artifacts.write(canvas, SWIM, USER, child.id)
    assert store.artifacts.get(art).head_version == 2
    assert store.artifacts.written_in(child.id) == [Written(art, 1, "Kế hoạch")]
    store.artifacts.write(art, PLAN, COACH, child.id)
    assert store.artifacts.written_in(child.id) == [Written(art, 3, "Kế hoạch")]


def test_a_deleted_canvas_is_no_longer_listed(store: Store):
    child = store.create()
    gone, kept = _began(store, child, "Bỏ"), _began(store, child, "Giữ")
    store.artifacts.delete(gone)
    assert store.artifacts.written_in(child.id) == [Written(kept, 1, "Giữ")]


def test_canvases_come_in_the_order_each_was_first_written_within_one_second(
    store: Store, canvas_clock, monkeypatch
):
    """Every write here carries the same timestamp. The order is neither that of the ids nor
    of the titles, and a later write to the first canvas does not move it back."""
    child = store.create()
    ids = iter(["b" * 12, "c" * 12, "a" * 12])
    monkeypatch.setattr("my_agent_crew.store.artifacts.new_id", lambda: next(ids))
    first, second, third = (_began(store, child, title) for title in ("B", "C", "A"))
    store.artifacts.write(first, SWIM, COACH, child.id)
    assert store.artifacts.written_in(child.id) == [
        Written(first, 2, "B"),
        Written(second, 1, "C"),
        Written(third, 1, "A"),
    ]


async def test_a_file_the_agent_imports_is_its_writing_as_a_new_canvas_or_a_new_version(
    store: Store, root: Path
):
    kept = agents_canvas(store, "coach", PLAN)
    child = child_turn(store, store.create())
    new = await call(store, "artifact_import", {"path": FILE, "title": "Từ tệp"}, root=root)
    made, version, _ = tagged(new)
    put(root, FILE, SWIM)
    over = {"id": kept, "path": FILE, "replace": True}
    assert tagged(await call(store, "artifact_import", over, root=root)) == (kept, 2, False)
    assert store.artifacts.head(kept).note == IMPORT_NOTE
    assert store.artifacts.written_in(child.id) == [
        Written(made, version, "Từ tệp"),
        Written(kept, 2, "Kế hoạch"),
    ]


async def test_carrying_a_canvas_to_or_from_a_file_unchanged_writes_nothing(
    store: Store, root: Path
):
    """An export, an import that finds the file and the canvas alike, and the place of that
    file being recorded on the canvas add no version, so the conversation wrote nothing."""
    kept = agents_canvas(store, "coach", PLAN)
    child = child_turn(store, store.create())
    same = await call(store, "artifact_import", {"id": kept, "path": FILE}, root=root)
    out = await call(store, "artifact_export", {"id": kept, "path": "out/plan.md"}, root=root)
    assert (same.ok, out.ok) == (True, True), (same.output, out.output)
    canvas = store.artifacts.get(kept)
    assert (canvas.head_version, canvas.source) == (1, f"workspace:coach/{FILE}")
    assert (root / "out/plan.md").read_text(encoding="utf-8") == PLAN
    assert store.artifacts.written_in(child.id) == []


def test_a_file_the_person_reads_again_on_the_web_is_not_the_agents_writing(
    deps_factory, store: Store
):
    """The web's import is the person's version, from no conversation: the canvas moves on
    and what the agent wrote in the conversation is what it was."""
    deps, child = deps_factory(), store.create()
    put(deps.agent.workspace, FILE, SWIM)
    art = store.artifacts.create(
        "Kế hoạch",
        "markdown",
        DEFAULT_AGENT_ID,
        f"agent:{DEFAULT_AGENT_ID}",
        child.id,
        PLAN,
        source=f"workspace:{DEFAULT_AGENT_ID}/{FILE}",
    ).id
    with TestClient(create_app(deps, schedule=False), base_url="http://127.0.0.1") as client:
        answer = client.post(f"/api/artifacts/{art}/reimport", json={"base_version": 1})
    assert (answer.status_code, answer.json()["changed"]) == (200, True)
    head = store.artifacts.head(art)
    assert (head.version, head.author, head.note) == (2, USER, IMPORT_NOTE)
    assert store.artifacts.written_in(child.id) == [Written(art, 1, "Kế hoạch")]
