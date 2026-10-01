"""How a canvas keeps its history: every write is a full version under a number that is never
reused, a person's autosaves within one burst share a row, and nothing an agent wrote or saw
is ever folded away."""

import sqlite3
from datetime import datetime

import pytest

from my_agent_crew.artifacts.kinds import ArtifactTooLarge, cap_bytes
from my_agent_crew.store.artifact_models import USER, VersionConflict
from my_agent_crew.store.artifact_versions import COALESCE_WINDOW_S
from my_agent_crew.store.db import Store

AGENT = "agent:default"


def _canvas(store: Store, author: str = AGENT, content: str = "# v1"):
    return store.artifacts.create("Kế hoạch", "markdown", "default", author, "c1", content)


def _rows(store: Store, artifact_id: str) -> list[tuple[int, str]]:
    return [(v.version, v.author) for v in store.artifacts.versions(artifact_id)]


def _seconds(start: str, end: str) -> float:
    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


def test_thirty_saves_in_a_minute_that_nobody_has_seen_keep_one_version(store, canvas_clock):
    art = _canvas(store)
    began = ""
    for n in range(30):
        canvas_clock.tick(2)
        began = began or canvas_clock.now
        store.artifacts.write(art.id, f"# save {n}", USER, "c1")

    assert _rows(store, art.id) == [(1, AGENT), (31, USER)]
    head = store.artifacts.head(art.id)
    assert head.content == "# save 29"
    assert (head.created_at, head.updated_at) == (began, canvas_clock.now)


def test_folding_a_save_in_gives_it_a_new_number_and_keeps_when_the_burst_began(
    store, canvas_clock
):
    art = _canvas(store, author=USER)
    began = store.artifacts.head(art.id).created_at
    canvas_clock.tick(5)

    folded = store.artifacts.write(art.id, "# b", USER, "c1", base_version=1)

    assert folded.version == 2
    assert (folded.created_at, folded.updated_at) == (began, canvas_clock.now)
    with pytest.raises(KeyError):
        store.artifacts.version(art.id, 1)
    # A second tab still holding version 1 learns it is behind instead of writing over it.
    with pytest.raises(VersionConflict) as caught:
        store.artifacts.write(art.id, "# c", USER, "c1", base_version=1)
    assert (caught.value.head_version, caught.value.head_content) == (2, "# b")


def test_a_persons_first_save_after_an_agents_version_opens_a_new_row(store, canvas_clock):
    art = _canvas(store)
    canvas_clock.tick(1)
    store.artifacts.write(art.id, "# mine", USER, "c1")
    assert _rows(store, art.id) == [(1, AGENT), (2, USER)]
    assert store.artifacts.version(art.id, 1).content == "# v1"


def test_an_agents_write_never_folds_a_persons_burst_away(store, canvas_clock):
    art = _canvas(store, author=USER, content="# typed")
    canvas_clock.tick(1)
    store.artifacts.write(art.id, "# agent", AGENT, "c1")
    assert _rows(store, art.id) == [(1, USER), (2, AGENT)]
    assert store.artifacts.version(art.id, 1).content == "# typed"


def test_a_burst_that_never_pauses_still_closes_its_row_after_the_window(store, canvas_clock):
    """A window that slid with every save would fold an hour of typing into a single row."""
    art = _canvas(store, author=USER)
    for n in range(40):
        canvas_clock.tick(10)
        store.artifacts.write(art.id, f"# {n}", USER, "c1")

    rows = store.artifacts.versions(art.id)
    assert len(rows) >= 2
    for row in rows:
        assert _seconds(row.created_at, row.updated_at) <= COALESCE_WINDOW_S


def test_a_clock_set_back_does_not_hold_a_burst_open(store, canvas_clock):
    """Once the clock is set back an hour every save looks younger than the burst's start,
    and a window with no floor would fold the whole next hour into one row."""
    art = _canvas(store, author=USER)
    canvas_clock.tick(-3600)
    for n in range(40):
        canvas_clock.tick(10)
        store.artifacts.write(art.id, f"# {n}", USER, "c1")
    assert len(store.artifacts.versions(art.id)) >= 2


def test_a_version_an_agent_has_seen_is_never_folded_into_the_next_save(store, canvas_clock):
    art = _canvas(store, author=USER)
    canvas_clock.tick(1)
    store.artifacts.write(art.id, "# draft", USER, "c1")
    store.artifact_links.mark_seen("c2", art.id, 2)
    canvas_clock.tick(1)

    store.artifacts.write(art.id, "# after", USER, "c1")

    assert _rows(store, art.id) == [(2, USER), (3, USER)]
    assert store.artifacts.version(art.id, 2).content == "# draft"


def test_a_restore_stays_its_own_row_and_the_next_save_opens_another(store, canvas_clock):
    art = _canvas(store, author=USER, content="# one")
    canvas_clock.tick(COALESCE_WINDOW_S + 60)
    store.artifacts.write(art.id, "# two", USER, "c1")
    canvas_clock.tick(1)
    restored = store.artifacts.restore(art.id, 1, USER, "c1")
    canvas_clock.tick(1)
    store.artifacts.write(art.id, "# three", USER, "c1")

    assert _rows(store, art.id) == [(1, USER), (2, USER), (3, USER), (4, USER)]
    assert store.artifacts.version(art.id, 2).content == "# two"
    assert (restored.version, restored.content, restored.note) == (3, "# one", "restore:1")
    assert store.artifacts.version(art.id, 3).note == "restore:1"


def test_interleaved_writes_keep_one_row_per_change_of_author(store, canvas_clock):
    art = _canvas(store)
    authors = [USER, USER, AGENT, USER, USER, USER, AGENT, AGENT]
    for n, author in enumerate(authors):
        canvas_clock.tick(2)
        store.artifacts.write(art.id, f"# {n}", author, "c1")

    rows = _rows(store, art.id)
    assert [author for _, author in rows] == [AGENT, USER, AGENT, USER, AGENT, AGENT]
    assert store.artifacts.get(art.id).head_version == 1 + len(authors)
    assert [number for number, _ in rows] == sorted({number for number, _ in rows})


def test_a_write_against_a_stale_base_is_refused_with_the_newest_version(store):
    art = _canvas(store)
    store.artifacts.write(art.id, "# v2", AGENT, "c1", base_version=1)
    with pytest.raises(VersionConflict) as caught:
        store.artifacts.write(art.id, "# mine", USER, "c1", base_version=1)
    assert (caught.value.head_version, caught.value.head_content) == (2, "# v2")
    assert store.artifacts.head(art.id).content == "# v2"


def test_apply_reads_changes_and_writes_in_one_step(store):
    art = _canvas(store, content="# a\nb")
    version = store.artifacts.apply(art.id, lambda text: text.replace("b", "c"), AGENT, "c1")
    assert (version.version, version.content, version.author) == (2, "# a\nc", AGENT)
    assert store.artifacts.head(art.id).content == "# a\nc"


def test_apply_writes_nothing_when_the_change_fails(store):
    art = _canvas(store)

    def fail(text: str) -> str:
        raise ValueError("old text not found")

    with pytest.raises(ValueError, match="old text not found"):
        store.artifacts.apply(art.id, fail, AGENT, "c1")
    assert _rows(store, art.id) == [(1, AGENT)]


def test_apply_writes_nothing_when_the_result_is_over_the_cap(store):
    art = _canvas(store)
    with pytest.raises(ArtifactTooLarge):
        store.artifacts.apply(art.id, lambda text: "x" * (cap_bytes("markdown") + 1), AGENT, "")
    assert _rows(store, art.id) == [(1, AGENT)]


def test_line_breaks_are_stored_as_lf_on_every_write_path(store):
    art = store.artifacts.create("t", "markdown", "default", AGENT, "c1", "a\r\nb\rc")
    assert store.artifacts.head(art.id).content == "a\nb\nc"
    written = store.artifacts.write(art.id, "d\r\ne", AGENT, "c1")
    applied = store.artifacts.apply(art.id, lambda text: text + "\r\nf", AGENT, "c1")
    assert (written.content, applied.content) == ("d\ne", "d\ne\nf")
    assert applied.size == len("d\ne\nf")


def test_restore_writes_the_old_text_as_a_new_version_and_keeps_the_later_ones(store):
    art = _canvas(store, content="# one")
    store.artifacts.write(art.id, "# two", AGENT, "c1")
    restored = store.artifacts.restore(art.id, 1, USER, "c9")
    assert (restored.version, restored.content, restored.note) == (3, "# one", "restore:1")
    assert (restored.author, restored.conversation_id) == (USER, "c9")
    assert _rows(store, art.id) == [(1, AGENT), (2, AGENT), (3, USER)]


class _AddingAVersionFails:
    """The store's connection, except that adding a version fails as a full disk would."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def execute(self, sql: str, params: tuple = ()):
        if sql.startswith("INSERT INTO artifact_versions"):
            raise sqlite3.OperationalError("disk I/O error")
        return self._conn.execute(sql, params)

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


def test_a_save_that_fails_halfway_through_folding_loses_nothing(store, canvas_clock):
    art = _canvas(store, author=USER)
    canvas_clock.tick(1)
    store.artifacts._conn = _AddingAVersionFails(store._conn)
    with pytest.raises(sqlite3.OperationalError):
        store.artifacts.write(art.id, "# b", USER, "c1")
    store.artifacts._conn = store._conn

    assert _rows(store, art.id) == [(1, USER)]
    assert store.artifacts.head(art.id).content == "# v1"
    assert store.artifacts.get(art.id).head_version == 1
