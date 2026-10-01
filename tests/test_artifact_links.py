"""Links between canvases and conversations, and the canvas each conversation has open. Every
write names a conversation and a canvas that both exist, or stores nothing."""

import pytest

from my_agent_crew.store.db import Store

SELECTION = {"version": 3, "text": "đoạn này", "line_start": 4, "line_end": 5}


def _canvas(store: Store, conversation_id: str = "", title: str = "Kế hoạch") -> str:
    agent = "agent:default"
    return store.artifacts.create(title, "markdown", "default", agent, conversation_id, "#").id


@pytest.fixture
def pair(store: Store) -> tuple[str, str]:
    """A conversation and a canvas, both real rows."""
    conv = store.create()
    return conv.id, _canvas(store, conv.id)


def test_linking_twice_keeps_what_the_conversation_has_already_seen(store: Store, pair):
    links, (conv, art) = store.artifact_links, pair
    links.link(conv, art)
    links.mark_seen(conv, art, 4)
    again = links.link(conv, art)
    assert (again.artifact_id, again.seen_version) == (art, 4)
    assert links.links_for(conv) == [again]


def test_a_fresh_link_has_seen_and_read_nothing(store: Store, pair):
    link = store.artifact_links.link(*pair)
    assert (link.seen_version, link.read_version, link.read_upto) == (0, 0, 0)
    assert link.linked_at
    assert store.artifact_links.links_for(pair[0]) == [link]


def test_sharing_only_ever_turns_on_and_reading_never_turns_it_on(store: Store, pair):
    """A shared link puts the canvas in reach of the conversation's delegated children; a
    read must not, or what one child read would widen what the next child can reach."""
    links, (conv, art) = store.artifact_links, pair
    assert links.link(conv, art).shared is False
    assert links.link(conv, art, shared=True).shared is True
    assert links.link(conv, art).shared is True

    other = store.create().id
    links.mark_seen(other, art, 1)
    links.mark_read(other, art, 1, 0, 1, 1)
    assert links.get(other, art).shared is False
    assert links.link(other, art, shared=True).seen_version == 1


def test_getting_a_link_never_makes_one(store: Store, pair):
    links, (conv, art) = store.artifact_links, pair
    assert links.get(conv, art) is None
    assert _stored(store) == (0, 0)
    made = links.link(conv, art)
    assert links.get(conv, art) == made


def test_seen_version_never_moves_back(store: Store, pair):
    links, (conv, art) = store.artifact_links, pair
    links.mark_seen(conv, art, 5)
    assert links.mark_seen(conv, art, 2).seen_version == 5
    assert [link.seen_version for link in links.links_for(conv)] == [5]


def test_marking_seen_links_a_canvas_the_conversation_did_not_know(store: Store, pair):
    conv, art = pair
    assert store.artifact_links.mark_seen(conv, art, 1).seen_version == 1
    assert store.artifact_links.conversations_for(art) == [conv]


def test_links_come_back_in_the_order_they_were_made(store: Store):
    links = store.artifact_links
    first, second = store.create().id, store.create().id
    b, a = _canvas(store, title="b"), _canvas(store, title="a")
    links.link(first, b)
    links.link(first, a)
    links.link(second, a)
    assert [link.artifact_id for link in links.links_for(first)] == [b, a]
    assert links.conversations_for(a) == [first, second]


def _stored(store: Store) -> tuple[int, int]:
    links = store._conn.execute("SELECT COUNT(*) FROM conversation_artifacts").fetchone()[0]
    focus = store._conn.execute("SELECT COUNT(*) FROM canvas_focus").fetchone()[0]
    return links, focus


def _write_every_way(store: Store, conv: str, art: str) -> list:
    links = store.artifact_links
    return [
        links.link(conv, art),
        links.mark_seen(conv, art, 1),
        links.mark_read(conv, art, 1, 0, 1, 1),
        links.set_focus(conv, art, SELECTION),
    ]


def test_nothing_links_a_conversation_or_canvas_that_does_not_exist(store: Store, pair):
    conv, art = pair
    assert _write_every_way(store, "no-such-conversation", art) == [None, None, None, False]
    assert _write_every_way(store, conv, "no-such-canvas") == [None, None, None, False]
    assert _stored(store) == (0, 0)


def test_a_late_write_after_a_delete_leaves_no_orphan_row(store: Store, pair):
    """A turn still running, a delegated child or a stale tab can write after the
    conversation or the canvas is gone; the row would otherwise stay forever."""
    conv, art = pair
    store.delete(conv)
    assert _write_every_way(store, conv, art) == [None, None, None, False]

    other = store.create().id
    store.artifacts.delete(art)
    assert _write_every_way(store, other, art) == [None, None, None, False]
    assert _stored(store) == (0, 0)


def test_pinned_once_some_conversation_has_seen_or_is_reading_that_version(store: Store, pair):
    links, (conv, art) = store.artifact_links, pair
    other = store.create().id
    links.link(conv, art)
    assert not links.pinned(art, 1)

    links.mark_seen(other, art, 3)
    assert links.pinned(art, 3) and links.pinned(art, 2)
    assert not links.pinned(art, 4)

    links.mark_read(conv, art, 5, 0, 10, 100)
    assert links.pinned(art, 5)
    assert not links.pinned(art, 6)
    assert not links.pinned(_canvas(store), 1)


def test_an_uncommitted_mark_is_undone_with_the_callers_transaction(store: Store, pair):
    links, (conv, art) = store.artifact_links, pair
    links.link(conv, art)
    with store._lock:
        links.mark_seen(conv, art, 7, commit=False)
        links.mark_read(conv, art, 7, 0, 5, 5, commit=False)
        store._conn.rollback()
    [link] = links.links_for(conv)
    assert (link.seen_version, link.read_version, link.read_upto) == (0, 0, 0)


def test_focus_holds_the_open_canvas_and_the_selected_passage(store: Store, pair):
    links, (conv, art) = store.artifact_links, pair
    assert links.focus(conv) is None
    assert links.set_focus(conv, art, SELECTION) is True
    focus = links.focus(conv)
    assert (focus.artifact_id, focus.selection) == (art, SELECTION)

    second = _canvas(store, conv)
    links.set_focus(conv, second, None)
    focus = links.focus(conv)
    assert (focus.artifact_id, focus.selection) == (second, None)


def test_clearing_the_selection_keeps_the_canvas_open(store: Store, pair):
    links, (conv, art) = store.artifact_links, pair
    links.set_focus(conv, art, SELECTION)
    links.clear_selection(conv)
    focus = links.focus(conv)
    assert (focus.artifact_id, focus.selection) == (art, None)

    links.clear_focus(conv)
    assert links.focus(conv) is None


def test_deleting_a_conversation_drops_its_links_and_focus_but_keeps_the_canvas(store: Store):
    conv = store.create()
    other = store.create()
    art = _canvas(store, conv.id)
    store.artifact_links.mark_seen(conv.id, art, 1)
    store.artifact_links.mark_seen(other.id, art, 1)
    store.artifact_links.set_focus(conv.id, art, SELECTION)

    store.delete(conv.id)

    assert store.artifact_links.links_for(conv.id) == []
    assert store.artifact_links.focus(conv.id) is None
    assert store.artifact_links.conversations_for(art) == [other.id]
    assert store.artifacts.get(art).title == "Kế hoạch"
