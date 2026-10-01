"""How a paged read marks what a conversation's agent has seen. The cursor counts characters of
one version read from the start without a gap; only a cursor that reaches the end of that
version makes it seen, so pages taken from two versions never pass for one whole read."""

import pytest

from my_agent_crew.store.db import Store


@pytest.fixture
def pair(store: Store) -> tuple[str, str]:
    conv = store.create()
    art = store.artifacts.create("Kế hoạch", "markdown", "default", "agent:default", conv.id, "#")
    return conv.id, art.id


def _read(store: Store, pair, version: int, start: int, end: int, total: int = 30):
    link = store.artifact_links.mark_read(*pair, version, start, end, total)
    return link.read_version, link.read_upto, link.seen_version


def test_reading_from_the_start_of_a_newer_version_starts_the_cursor_over(store: Store, pair):
    assert _read(store, pair, 2, 0, 10) == (2, 10, 0)
    assert _read(store, pair, 3, 0, 5) == (3, 5, 0)


def test_a_page_that_begins_inside_what_was_read_extends_the_cursor(store: Store, pair):
    _read(store, pair, 2, 0, 10)
    assert _read(store, pair, 2, 10, 20) == (2, 20, 0)
    assert _read(store, pair, 2, 5, 15) == (2, 20, 0)
    assert _read(store, pair, 2, 0, 12) == (2, 20, 0)


def test_a_page_that_skips_ahead_or_an_older_version_moves_nothing(store: Store, pair):
    _read(store, pair, 2, 0, 10)
    assert _read(store, pair, 2, 15, 20) == (2, 10, 0)
    assert _read(store, pair, 1, 0, 30) == (2, 10, 0)


def test_a_version_read_to_its_end_without_a_gap_is_seen(store: Store, pair):
    assert _read(store, pair, 2, 0, 10) == (2, 10, 0)
    assert _read(store, pair, 2, 10, 30) == (2, 30, 2)
    assert _read(store, pair, 4, 0, 30) == (4, 30, 4)


def test_pages_taken_from_two_versions_never_count_as_one_whole_read(store: Store, pair):
    """Page 1 of v2, then a person's save makes v3 and page 2 comes from it: the agent has
    read neither version whole, and a rewrite from what it read would lose the save."""
    _read(store, pair, 2, 0, 10)
    assert _read(store, pair, 3, 10, 30) == (2, 10, 0)


def test_an_empty_version_is_seen_by_reading_it_once(store: Store, pair):
    assert _read(store, pair, 1, 0, 0, total=0) == (1, 0, 1)


def test_reading_an_older_version_whole_never_moves_seen_back(store: Store, pair):
    store.artifact_links.mark_seen(*pair, 5)
    assert _read(store, pair, 3, 0, 30) == (3, 30, 5)
