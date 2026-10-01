"""What the canvas store refuses whoever calls it: a title that is not one line of visible
text, a language that is not one short name, an author that is neither the person nor an
agent, a creator that does not match its author, and a write that would take every canvas
together past its author's ceiling, which for an agent stops short of the person's so the
person can always save. A refused write stores nothing."""

import pytest

from my_agent_crew.artifacts.kinds import (
    LANGUAGE_MAX,
    TITLE_MAX,
    InvalidLanguage,
    InvalidTitle,
    StorageFull,
)
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store

AGENT = "agent:default"


def _create(store: Store, title: str = "Kế hoạch", content: str = "# a", author: str = AGENT):
    creator = "" if author == USER else author.removeprefix("agent:")
    return store.artifacts.create(title, "markdown", creator, author, "c1", content)


def _versions(store: Store, artifact_id: str) -> list[int]:
    return [v.version for v in store.artifacts.versions(artifact_id)]


def test_every_way_of_setting_a_title_stores_it_cleaned(store: Store):
    art = _create(store, title="  Kế\nhoạch‮ ")
    assert art.title == "Kế hoạch"
    store.artifacts.write(art.id, "# b", AGENT, "c1", title="Bản\r\nhai")
    assert store.artifacts.get(art.id).title == "Bản hai"
    store.artifacts.apply(art.id, lambda head: head.content.upper(), AGENT, "c1", title="\tBản ba⁦")
    assert store.artifacts.get(art.id).title == "Bản ba"
    assert store.artifacts.rename(art.id, "Bản bốn").title == "Bản bốn"


def test_a_bad_title_refuses_the_whole_write(store: Store):
    art = _create(store)
    with pytest.raises(InvalidTitle):
        _create(store, title="\n​")
    with pytest.raises(InvalidTitle):
        store.artifacts.write(art.id, "# b", AGENT, "c1", title=" ")
    with pytest.raises(InvalidTitle):
        store.artifacts.apply(
            art.id, lambda head: head.content.upper(), AGENT, "c1", title="x" * (TITLE_MAX + 1)
        )
    with pytest.raises(InvalidTitle):
        store.artifacts.rename(art.id, "")

    assert [a.id for a in store.artifacts.list()] == [art.id]
    assert _versions(store, art.id) == [1]
    assert (store.artifacts.get(art.id).title, store.artifacts.head(art.id).content) == (
        "Kế hoạch",
        "# a",
    )


@pytest.mark.parametrize(
    "author", ["default", "agent:", "", "User", "users", " user", "agent:Coach", "agent:x\n"]
)
def test_an_author_that_is_neither_the_person_nor_an_agent_is_refused(store: Store, author):
    """A bare agent id would read as the person's version were an agent ever named "user"."""
    art = _create(store)
    with pytest.raises(ValueError, match="author"):
        _create(store, author=author)
    with pytest.raises(ValueError, match="author"):
        store.artifacts.write(art.id, "# b", author, "c1")
    with pytest.raises(ValueError, match="author"):
        store.artifacts.restore(art.id, 1, author, "c1")
    assert [a.id for a in store.artifacts.list()] == [art.id]
    assert _versions(store, art.id) == [1]


def test_the_person_and_any_named_agent_may_write(store: Store):
    art = _create(store, author=USER)
    store.artifacts.write(art.id, "# b", "agent:coach", "c1")
    store.artifacts.write(art.id, "# c", "agent:user", "c1")
    authors = [v.author for v in store.artifacts.versions(art.id)]
    assert authors == [USER, "agent:coach", "agent:user"]
    assert (art.agent_id, _create(store, author="agent:user").agent_id) == ("", "user")


@pytest.mark.parametrize(
    ("agent_id", "author"),
    [
        ("user", USER),  # the person's canvas would pass for one an agent named "user" made
        ("default", USER),
        ("", "agent:default"),
        ("coach", "agent:ledger"),  # one agent's canvas filed under another
        ("Coach", "agent:Coach"),
        ("coach\n", "agent:coach\n"),
    ],
)
def test_a_creator_that_does_not_match_its_author_is_refused(store: Store, agent_id, author):
    with pytest.raises(ValueError, match="author"):
        store.artifacts.create("Kế hoạch", "markdown", agent_id, author, "c1", "# a")
    assert store.artifacts.list() == []


def _code(store: Store, language: str):
    return store.artifacts.create("Mã", "code", "default", AGENT, "c1", "x = 1", language=language)


def test_a_language_is_stored_as_one_short_lower_case_name(store: Store):
    assert _code(store, " Python ").language == "python"
    assert _code(store, "").language == ""


@pytest.mark.parametrize(
    "language", ["c\nsharp", "visual basic", "py\u202e", "x" * (LANGUAGE_MAX + 1)]
)
def test_a_language_that_is_not_one_short_name_refuses_the_canvas(store: Store, language):
    """It is quoted to a model beside the title, so it must not end that line or hide text."""
    with pytest.raises(InvalidLanguage):
        _code(store, language)
    assert store.artifacts.list() == []


@pytest.fixture
def ten_bytes(monkeypatch) -> int:
    """Ten bytes in all: the person may fill every one of them, an agent nine."""
    monkeypatch.setattr("my_agent_crew.store.artifacts.STORAGE_CAP", 10)
    return 10


@pytest.mark.parametrize(("author", "ceiling"), [(USER, 10), (AGENT, 9)])
def test_a_write_past_its_authors_ceiling_is_refused_and_stores_nothing(
    store: Store, ten_bytes, author, ceiling
):
    art = _create(store, content="aaaaaa")
    with pytest.raises(StorageFull) as caught:
        _create(store, content="bbbbb", author=author)
    assert (caught.value.used, caught.value.cap) == (6, ceiling)
    with pytest.raises(StorageFull):
        store.artifacts.write(art.id, "ccccc", author, "c1")
    with pytest.raises(StorageFull):
        store.artifacts.restore(art.id, 1, author, "c1")

    assert [a.id for a in store.artifacts.list()] == [art.id]
    assert _versions(store, art.id) == [1]
    assert store.artifacts.sizes() == {art.id: 6}


def test_a_write_that_lands_exactly_on_its_authors_ceiling_still_fits(store: Store, ten_bytes):
    art = _create(store, content="aaaaaa")
    store.artifacts.write(art.id, "bbb", AGENT, "c1")
    assert store.artifacts.sizes() == {art.id: 9}
    store.artifacts.write(art.id, "c", USER, "c1")
    assert store.artifacts.sizes() == {art.id: ten_bytes}


def test_agents_stop_short_of_the_ceiling_so_the_person_can_still_save(store: Store, ten_bytes):
    """A writer stuck in a loop fills the store only as far as its own ceiling, and the person
    typing in a canvas can still save what they typed."""
    art = _create(store, content="aaaaaa")
    store.artifacts.write(art.id, "bbb", AGENT, "c1")
    with pytest.raises(StorageFull) as caught:
        store.artifacts.write(art.id, "c", "agent:coach", "c1")
    assert (caught.value.used, caught.value.cap) == (9, 9)
    with pytest.raises(StorageFull):
        _create(store, content="c")

    store.artifacts.write(art.id, "c", USER, "c1")
    assert _versions(store, art.id) == [1, 2, 3]
    assert store.artifacts.sizes() == {art.id: ten_bytes}


def test_a_save_that_folds_into_the_burst_counts_only_what_it_adds(
    store: Store, canvas_clock, ten_bytes
):
    """The folded row is deleted in the same step, so the person can keep typing on a
    document that already sits near the ceiling."""
    art = _create(store, content="aaaaaa", author=USER)
    canvas_clock.tick(1)
    store.artifacts.write(art.id, "bbbbbbb", USER, "c1")
    assert store.artifacts.sizes() == {art.id: 7}
    with pytest.raises(StorageFull):
        store.artifacts.write(art.id, "cccc", AGENT, "c1")
