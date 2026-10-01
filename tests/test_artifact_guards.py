"""What the canvas store refuses whoever calls it: a title that is not one line of visible
text, an author that is neither the person nor an agent, and a write that would take every
canvas together past the storage ceiling. A refused write stores nothing."""

import pytest

from my_agent_crew.artifacts.kinds import TITLE_MAX, InvalidTitle, StorageFull
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store

AGENT = "agent:default"


def _create(store: Store, title: str = "Kế hoạch", content: str = "# a", author: str = AGENT):
    return store.artifacts.create(title, "markdown", "default", author, "c1", content)


def _versions(store: Store, artifact_id: str) -> list[int]:
    return [v.version for v in store.artifacts.versions(artifact_id)]


def test_every_way_of_setting_a_title_stores_it_cleaned(store: Store):
    art = _create(store, title="  Kế\nhoạch‮ ")
    assert art.title == "Kế hoạch"
    store.artifacts.write(art.id, "# b", AGENT, "c1", title="Bản\r\nhai")
    assert store.artifacts.get(art.id).title == "Bản hai"
    store.artifacts.apply(art.id, str.upper, AGENT, "c1", title="\tBản ba⁦")
    assert store.artifacts.get(art.id).title == "Bản ba"
    assert store.artifacts.rename(art.id, "Bản bốn").title == "Bản bốn"


def test_a_bad_title_refuses_the_whole_write(store: Store):
    art = _create(store)
    with pytest.raises(InvalidTitle):
        _create(store, title="\n​")
    with pytest.raises(InvalidTitle):
        store.artifacts.write(art.id, "# b", AGENT, "c1", title=" ")
    with pytest.raises(InvalidTitle):
        store.artifacts.apply(art.id, str.upper, AGENT, "c1", title="x" * (TITLE_MAX + 1))
    with pytest.raises(InvalidTitle):
        store.artifacts.rename(art.id, "")

    assert [a.id for a in store.artifacts.list()] == [art.id]
    assert _versions(store, art.id) == [1]
    assert (store.artifacts.get(art.id).title, store.artifacts.head(art.id).content) == (
        "Kế hoạch",
        "# a",
    )


@pytest.mark.parametrize("author", ["default", "agent:", "", "User", "users", " user"])
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


@pytest.fixture
def ten_bytes(monkeypatch) -> int:
    monkeypatch.setattr("my_agent_crew.store.artifacts.STORAGE_CAP", 10)
    return 10


def test_a_write_past_the_storage_ceiling_is_refused_and_stores_nothing(store: Store, ten_bytes):
    art = _create(store, content="aaaaaa")
    with pytest.raises(StorageFull) as caught:
        _create(store, content="bbbbb")
    assert (caught.value.used, caught.value.cap) == (6, ten_bytes)
    with pytest.raises(StorageFull):
        store.artifacts.write(art.id, "ccccc", AGENT, "c1")
    with pytest.raises(StorageFull):
        store.artifacts.restore(art.id, 1, AGENT, "c1")

    assert [a.id for a in store.artifacts.list()] == [art.id]
    assert _versions(store, art.id) == [1]
    assert store.artifacts.sizes() == {art.id: 6}


def test_a_write_that_lands_exactly_on_the_ceiling_still_fits(store: Store, ten_bytes):
    art = _create(store, content="aaaaaa")
    store.artifacts.write(art.id, "bbbb", AGENT, "c1")
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
