"""The canvas API's table of refusals: each error the store raises becomes one status code and
a body the web can act on, caught in the order `canvas_errors` catches them. An error the table
does not name is a bug and passes on, to reach the client as a 500."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import HTTPException

from my_agent_crew.artifacts.kinds import cap_bytes
from my_agent_crew.server.artifact_errors import artifact_errors
from my_agent_crew.store.artifact_models import USER, VersionConflict


def _refusal(store, artifact_id: str, act: Callable[[], object]) -> HTTPException:
    with pytest.raises(HTTPException) as caught, artifact_errors(store.artifacts, artifact_id):
        act()
    return caught.value


def _raise(error: BaseException) -> Callable[[], object]:
    def act() -> object:
        raise error

    return act


def _canvas(store, content: str = "# a") -> str:
    return store.artifacts.create("Plan", "markdown", "coach", "agent:coach", "", content).id


def test_a_version_folded_away_is_404_with_the_newest_number_though_it_is_a_key_error(store):
    art = _canvas(store)
    store.artifacts.write(art, "# b", "agent:coach", "")
    refusal = _refusal(store, art, lambda: store.artifacts.version(art, 9))
    assert (refusal.status_code, refusal.detail) == (404, {"head_version": 2})


def test_a_missing_canvas_is_404_artifact_not_found(store):
    refusal = _refusal(store, "nope", lambda: store.artifacts.get("nope"))
    assert (refusal.status_code, refusal.detail) == (404, "artifact not found")


def test_a_key_error_naming_anything_else_passes_on_as_a_bug(store):
    art = _canvas(store)
    with pytest.raises(KeyError), artifact_errors(store.artifacts, art):
        store.artifacts.get("other")
    with pytest.raises(KeyError), artifact_errors(store.artifacts):
        raise KeyError("")


def test_a_value_error_the_table_does_not_name_passes_on_as_a_bug(store):
    art = _canvas(store)
    with pytest.raises(ValueError, match="author"), artifact_errors(store.artifacts, art):
        store.artifacts.write(art, "# b", "nobody", "")


def test_a_stale_base_version_is_409_with_the_newest_version_and_its_author(store):
    art = _canvas(store)
    store.artifacts.write(art, "# theirs", "agent:coach", "", base_version=1)
    write = lambda: store.artifacts.write(art, "# mine", USER, "", base_version=1)  # noqa: E731
    refusal = _refusal(store, art, write)
    assert refusal.status_code == 409
    assert refusal.detail == {"head_version": 2, "content": "# theirs", "author": "agent:coach"}
    assert store.artifacts.head(art).content == "# theirs"


def test_the_409_reads_the_newest_version_afresh_not_the_one_the_conflict_saw(store):
    art = _canvas(store)
    store.artifacts.write(art, "# b", "agent:coach", "")
    store.artifacts.write(art, "# c", "agent:coach", "")
    refusal = _refusal(store, art, _raise(VersionConflict(2, "# b")))
    assert refusal.detail == {"head_version": 3, "content": "# c", "author": "agent:coach"}


def test_a_conflict_on_a_canvas_deleted_meanwhile_is_404(store):
    refusal = _refusal(store, "gone", _raise(VersionConflict(1, "# a")))
    assert (refusal.status_code, refusal.detail) == (404, "artifact not found")


def test_a_version_over_its_kind_cap_is_413_with_size_and_cap(store):
    art = _canvas(store)
    cap = cap_bytes("markdown")
    refusal = _refusal(store, art, lambda: store.artifacts.write(art, "x" * (cap + 1), USER, ""))
    assert (refusal.status_code, refusal.detail) == (413, {"size": cap + 1, "cap": cap})
    assert store.artifacts.head(art).version == 1


def test_full_storage_is_507_naming_the_three_largest_canvases_biggest_first(store, monkeypatch):
    sizes = {"A": 10, "B": 40, "C": 30, "D": 20}
    ids = {
        title: store.artifacts.create(title, "markdown", "", USER, "", "x" * size).id
        for title, size in sizes.items()
    }
    monkeypatch.setattr("my_agent_crew.store.artifacts.STORAGE_CAP", 105)
    write = lambda: store.artifacts.write(ids["A"], "x" * 16, USER, "")  # noqa: E731
    refusal = _refusal(store, ids["A"], write)
    assert refusal.status_code == 507
    assert refusal.detail == {
        "used": 100,
        "cap": 105,
        "largest": [
            {"id": ids["B"], "title": "B", "size": 40},
            {"id": ids["C"], "title": "C", "size": 30},
            {"id": ids["D"], "title": "D", "size": 20},
        ],
    }


@pytest.mark.parametrize(
    "make",
    [
        lambda arts: arts.create("Plan", "pdf", "", USER, "", "x"),
        lambda arts: arts.create("Plan", "image", "", USER, "", "x"),
        lambda arts: arts.create("   ", "markdown", "", USER, "", "x"),
        lambda arts: arts.create("Plan", "code", "", USER, "", "x", language="py thon"),
    ],
    ids=["kind", "payload", "title", "language"],
)
def test_a_kind_payload_title_or_language_the_store_refuses_is_422_with_its_message(store, make):
    with pytest.raises(ValueError) as raw:
        make(store.artifacts)
    refusal = _refusal(store, "", lambda: make(store.artifacts))
    assert (refusal.status_code, refusal.detail) == (422, str(raw.value))
    assert store.artifacts.list() == []
