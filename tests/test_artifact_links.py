"""Links between canvases and conversations, and the canvas each conversation has open."""

from my_agent_crew.store.db import Store

SELECTION = {"version": 3, "text": "đoạn này", "line_start": 4, "line_end": 5}


def test_linking_twice_keeps_what_the_conversation_has_already_seen(store: Store):
    links = store.artifact_links
    links.link("c1", "a1")
    links.mark_seen("c1", "a1", 4)
    links.link("c1", "a1")
    [link] = links.links_for("c1")
    assert (link.artifact_id, link.seen_version) == ("a1", 4)


def test_a_fresh_link_has_seen_nothing(store: Store):
    store.artifact_links.link("c1", "a1")
    [link] = store.artifact_links.links_for("c1")
    assert link.seen_version == 0 and link.linked_at


def test_seen_version_never_moves_back(store: Store):
    links = store.artifact_links
    links.mark_seen("c1", "a1", 5)
    links.mark_seen("c1", "a1", 2)
    assert [link.seen_version for link in links.links_for("c1")] == [5]


def test_marking_seen_links_a_canvas_the_conversation_did_not_know(store: Store):
    store.artifact_links.mark_seen("c1", "a1", 1)
    assert store.artifact_links.conversations_for("a1") == ["c1"]


def test_links_come_back_in_the_order_they_were_made(store: Store):
    links = store.artifact_links
    links.link("c1", "b")
    links.link("c1", "a")
    links.link("c2", "a")
    assert [link.artifact_id for link in links.links_for("c1")] == ["b", "a"]
    assert links.conversations_for("a") == ["c1", "c2"]


def test_any_seen_is_true_only_once_some_conversation_reached_that_version(store: Store):
    links = store.artifact_links
    links.link("c1", "a1")
    assert not links.any_seen("a1", 1)
    links.mark_seen("c2", "a1", 3)
    assert links.any_seen("a1", 3)
    assert links.any_seen("a1", 2)
    assert not links.any_seen("a1", 4)
    assert not links.any_seen("other", 1)


def test_an_uncommitted_mark_is_undone_with_the_callers_transaction(store: Store):
    links = store.artifact_links
    links.link("c1", "a1")
    with store._lock:
        links.mark_seen("c1", "a1", 7, commit=False)
        store._conn.rollback()
    assert [link.seen_version for link in links.links_for("c1")] == [0]


def test_focus_holds_the_open_canvas_and_the_selected_passage(store: Store):
    links = store.artifact_links
    assert links.focus("c1") is None
    links.set_focus("c1", "a1", SELECTION)
    focus = links.focus("c1")
    assert (focus.artifact_id, focus.selection) == ("a1", SELECTION)

    links.set_focus("c1", "a2", None)
    focus = links.focus("c1")
    assert (focus.artifact_id, focus.selection) == ("a2", None)


def test_clearing_the_selection_keeps_the_canvas_open(store: Store):
    links = store.artifact_links
    links.set_focus("c1", "a1", SELECTION)
    links.clear_selection("c1")
    focus = links.focus("c1")
    assert (focus.artifact_id, focus.selection) == ("a1", None)

    links.clear_focus("c1")
    assert links.focus("c1") is None


def test_deleting_a_conversation_drops_its_links_and_focus_but_keeps_the_canvas(store: Store):
    conv = store.create()
    other = store.create()
    art = store.artifacts.create("Kế hoạch", "markdown", "default", "agent:default", conv.id, "# a")
    store.artifact_links.mark_seen(conv.id, art.id, 1)
    store.artifact_links.mark_seen(other.id, art.id, 1)
    store.artifact_links.set_focus(conv.id, art.id, SELECTION)

    store.delete(conv.id)

    assert store.artifact_links.links_for(conv.id) == []
    assert store.artifact_links.focus(conv.id) is None
    assert store.artifact_links.conversations_for(art.id) == [other.id]
    assert store.artifacts.get(art.id).title == "Kế hoạch"
