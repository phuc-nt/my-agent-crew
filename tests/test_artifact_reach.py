"""Which canvases an agent other than the master reaches from a conversation: those linked to
the conversation, those the root of its delegation shares, and those the agent created."""

import pytest

from my_agent_crew.store.db import Store

AGENT = "coach"


def _canvas(store: Store, title: str, agent_id: str = "") -> str:
    author = "user" if agent_id == "" else f"agent:{agent_id}"
    return store.artifacts.create(title, "markdown", agent_id, author, "", "#").id


def test_a_quiet_canvas_linked_here_is_found_past_newer_ones_out_of_reach(store: Store):
    """The scope is part of the query, so canvases out of reach never use up the limit."""
    here, elsewhere = store.create().id, store.create().id
    quiet = _canvas(store, "Cũ")
    store.artifact_links.link(here, quiet)
    for n in range(60):
        store.artifact_links.link(elsewhere, _canvas(store, f"Mới {n}"))
    assert [found.id for found in store.artifacts.reachable(here, "", AGENT)] == [quiet]


def test_reachable_and_is_reachable_agree_on_every_kind_of_canvas(store: Store):
    root, here, other = store.create().id, store.create().id, store.create().id
    links = store.artifact_links
    expected = {}

    def add(label: str, agent_id: str, link_to: str = "", shared: bool = False, *, reach: bool):
        art = _canvas(store, label, agent_id)
        if link_to:
            links.link(link_to, art, shared=shared)
        expected[art] = (label, reach)

    add("linked here", "", here, reach=True)
    add("shared by the root", "", root, shared=True, reach=True)
    add("only read in the root", "", root, reach=False)
    add("created by this agent", AGENT, reach=True)
    add("created by the person", "", reach=False)
    add("created by another agent", "ledger", reach=False)
    add("shared by another conversation", "", other, shared=True, reach=False)
    add("another agent's, linked here", "ledger", here, reach=True)

    found = {summary.id for summary in store.artifacts.reachable(here, root, AGENT, limit=100)}
    for art, (label, reach) in expected.items():
        assert (art in found) is reach, label
        assert store.artifacts.is_reachable(art, here, root, AGENT) is reach, label


def test_a_persons_canvas_is_reached_only_through_a_link_whatever_the_agent_is_called(
    store: Store,
):
    """A person's canvas is filed under agent "", which no agent id can be: not even an
    agent named after the author a person's versions carry."""
    here = store.create().id
    art = _canvas(store, "Của người")
    assert store.artifacts.reachable(here, "", "user") == []
    assert not store.artifacts.is_reachable(art, here, "", "user")
    for call in (
        lambda: store.artifacts.reachable(here, "", ""),
        lambda: store.artifacts.is_reachable(art, here, "", ""),
    ):
        with pytest.raises(ValueError):
            call()


def test_reachable_matches_the_title_without_case_or_accents_before_the_limit(store: Store):
    here = store.create().id
    plan = _canvas(store, "Kế hoạch tháng Mười", AGENT)
    for n in range(5):
        _canvas(store, f"Ghi chú {n}", AGENT)
    found = store.artifacts.reachable(here, "", AGENT, query="KE HOACH", limit=1)
    assert [summary.id for summary in found] == [plan]
    assert store.artifacts.reachable(here, "", AGENT, query="không có") == []


def test_reachable_lists_the_most_recently_changed_first(store: Store, canvas_clock):
    here = store.create().id
    first, second = _canvas(store, "Một", AGENT), _canvas(store, "Hai", AGENT)

    def order() -> list[str]:
        return [summary.id for summary in store.artifacts.reachable(here, "", AGENT)]

    assert order() == [second, first]  # made in the same second: the later row first
    canvas_clock.tick(2)
    store.artifacts.write(first, "# mới", f"agent:{AGENT}", here)
    assert order() == [first, second]
