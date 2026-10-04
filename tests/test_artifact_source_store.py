"""Where a canvas came from. A write may record the file a version was imported from together
with that version, an import that changed nothing records it alone, and a version that came
from a file stays a row of its own: a person's typing never folds into it, and it never folds
a burst of typing away. A picture canvas takes new bytes the same way and gives an old
picture back byte for byte."""

from __future__ import annotations

import pytest

from my_agent_crew.artifacts.kinds import PayloadMismatch
from my_agent_crew.store.artifact_models import IMPORT_NOTE, USER, VersionConflict
from my_agent_crew.store.db import Store
from tests.canvas_helpers import lock_is_free

AGENT = "agent:default"
SOURCE = "workspace:default/out/deck/index.html"
MOVED = "workspace:designer/out/deck/index.html"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(32))
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF" + bytes(range(32))


def _canvas(store: Store, source: str = SOURCE, author: str = AGENT):
    creator = "" if author == USER else author.removeprefix("agent:")
    return store.artifacts.create(
        "Deck", "html", creator, author, "c1", "<p>một</p>", source=source
    )


def _rows(store: Store, artifact_id: str) -> list[tuple[int, str, str]]:
    return [(v.version, v.author, v.note) for v in store.artifacts.versions(artifact_id)]


def _listen(store: Store) -> list[tuple]:
    """Every change the store announces from here on, with whether it had committed and let
    go of its lock by then."""
    heard: list[tuple] = []

    def on_change(summary: dict, conversation_ids: list[str]) -> None:
        free = lock_is_free(store)
        heard.append((summary, conversation_ids, store._conn.in_transaction, free))

    store.artifacts.on_change = on_change
    return heard


def test_a_write_records_where_its_version_came_from_in_the_one_change(store: Store):
    """The version and its source are announced together, so no listener ever sees the new
    text under the old source."""
    art = _canvas(store, source="")
    heard = _listen(store)
    written = store.artifacts.write(
        art.id, "<p>hai</p>", AGENT, "c1", base_version=1, note=IMPORT_NOTE, source=SOURCE
    )
    summary = store.artifacts.get(art.id)
    assert (written.version, written.note, written.content) == (2, IMPORT_NOTE, "<p>hai</p>")
    assert (summary.head_version, summary.source) == (2, SOURCE)
    assert [(s["head_version"], s["source"]) for s, _, _, _ in heard] == [(2, SOURCE)]


def test_a_write_that_names_no_source_keeps_the_one_recorded(store: Store):
    art = _canvas(store)
    store.artifacts.write(art.id, "<p>hai</p>", AGENT, "c1", title="Deck mới")
    store.artifacts.apply(art.id, lambda head: head.content.upper(), AGENT, "c1")
    store.artifacts.restore(art.id, 1, USER, "")
    summary = store.artifacts.get(art.id)
    assert (summary.head_version, summary.source, summary.title) == (4, SOURCE, "Deck mới")
    store.artifacts.write(art.id, "<p>ba</p>", AGENT, "c1", source=MOVED)
    assert store.artifacts.get(art.id).source == MOVED


def test_a_refused_write_leaves_the_source_as_it_was(store: Store):
    art = _canvas(store)
    store.artifacts.write(art.id, "<p>hai</p>", AGENT, "c1")
    with pytest.raises(VersionConflict):
        store.artifacts.write(art.id, "<p>ba</p>", USER, "", base_version=1, source=MOVED)
    assert store.artifacts.get(art.id).source == SOURCE
    assert _rows(store, art.id) == [(1, AGENT, ""), (2, AGENT, "")]


def test_setting_the_source_adds_no_version_and_keeps_the_time_of_the_last_change(
    store: Store, canvas_clock
):
    """An import that found the text unchanged still records a file that moved; the web hears
    of it, but the canvas does not climb the list as though someone had written to it."""
    art = _canvas(store)
    first, second = store.create().id, store.create().id
    store.artifact_links.link(first, art.id)
    store.artifact_links.link(second, art.id)
    heard = _listen(store)
    canvas_clock.tick(5)

    moved = store.artifacts.set_source(art.id, MOVED)

    assert (moved.source, moved.head_version, moved.title) == (MOVED, 1, "Deck")
    assert moved.updated_at == art.updated_at != canvas_clock.now
    assert store.artifacts.get(art.id) == moved
    assert _rows(store, art.id) == [(1, AGENT, "")]
    assert heard == [(moved.to_dict(), [first, second], False, True)]


def test_setting_the_source_of_a_canvas_that_is_gone_raises_key_error(store: Store):
    heard = _listen(store)
    with pytest.raises(KeyError) as caught:
        store.artifacts.set_source("nope", SOURCE)
    assert caught.value.args == ("nope",)
    assert heard == []


def test_typing_right_after_a_reimport_keeps_the_imported_version(store: Store, canvas_clock):
    """The person's save is theirs, like the import before it, and well inside the window: only
    the import's note keeps it from being folded away."""
    art = _canvas(store, author=USER)
    store.artifacts.write(art.id, "<p>từ tệp</p>", USER, "", note=IMPORT_NOTE)
    canvas_clock.tick(1)
    store.artifacts.write(art.id, "<p>gõ</p>", USER, "")
    canvas_clock.tick(1)
    store.artifacts.write(art.id, "<p>gõ tiếp</p>", USER, "")

    assert _rows(store, art.id) == [(1, USER, ""), (2, USER, IMPORT_NOTE), (4, USER, "")]
    assert store.artifacts.version(art.id, 2).content == "<p>từ tệp</p>"


def test_a_reimport_right_after_a_burst_of_typing_keeps_what_was_typed(store: Store, canvas_clock):
    art = _canvas(store, author=USER)
    canvas_clock.tick(1)
    store.artifacts.write(art.id, "<p>gõ</p>", USER, "")
    canvas_clock.tick(1)
    store.artifacts.write(art.id, "<p>từ tệp</p>", USER, "", note=IMPORT_NOTE)

    assert _rows(store, art.id) == [(2, USER, ""), (3, USER, IMPORT_NOTE)]
    assert store.artifacts.version(art.id, 2).content == "<p>gõ</p>"


def test_a_picture_canvas_takes_new_bytes_and_keeps_the_old_ones(store: Store):
    art = store.artifacts.create("Logo", "image", "default", AGENT, "c1", data=PNG)
    written = store.artifacts.write(art.id, None, AGENT, "c1", note=IMPORT_NOTE, data=JPEG)
    assert (written.version, written.data, written.content) == (2, JPEG, None)
    assert written.size == len(JPEG)
    assert store.artifacts.head(art.id).data == JPEG
    assert store.artifacts.version(art.id, 1).data == PNG


@pytest.mark.parametrize(
    ("kind", "content", "data"),
    [
        ("image", "chữ", None),
        ("image", "chữ", JPEG),
        ("image", None, None),
        ("markdown", None, b"# b"),
        ("markdown", "# b", b"# b"),
    ],
)
def test_a_write_whose_payload_does_not_fit_the_kind_adds_no_version(
    store: Store, kind: str, content: str | None, data: bytes | None
):
    first = {"data": PNG} if kind == "image" else {"content": "# a"}
    art = store.artifacts.create("t", kind, "default", AGENT, "c1", **first)
    with pytest.raises(PayloadMismatch):
        store.artifacts.write(art.id, content, AGENT, "c1", data=data)
    assert [v.version for v in store.artifacts.versions(art.id)] == [1]


def test_restoring_a_picture_brings_back_its_exact_bytes(store: Store):
    art = store.artifacts.create("Logo", "image", "", USER, "", data=PNG)
    store.artifacts.write(art.id, None, USER, "", note=IMPORT_NOTE, data=JPEG)
    restored = store.artifacts.restore(art.id, 1, USER, "")
    assert (restored.version, restored.data, restored.content) == (3, PNG, None)
    assert (restored.note, restored.size) == ("restore:1", len(PNG))
    assert store.artifacts.head(art.id).data == PNG
    assert store.artifacts.version(art.id, 2).data == JPEG
