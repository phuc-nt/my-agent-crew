"""Creating, reading, listing, renaming and deleting canvases, and the callback that tells the
rest of the app a canvas changed."""

import logging

import pytest

from my_agent_crew.artifacts.kinds import (
    ArtifactTooLarge,
    NotAnImage,
    PayloadMismatch,
    UnknownKind,
    cap_bytes,
)
from my_agent_crew.store.artifact_models import USER, VersionGone
from my_agent_crew.store.db import Store
from tests.canvas_helpers import lock_is_free

AGENT = "agent:default"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(16)


def _create(store: Store, title: str = "Kế hoạch", content: str = "# a", **kwargs):
    kwargs = {"agent_id": "default", "author": AGENT, "conversation_id": "c1", **kwargs}
    return store.artifacts.create(title, "markdown", content=content, **kwargs)


def _titles(summaries) -> list[str]:
    return [summary.title for summary in summaries]


def test_a_new_canvas_starts_at_version_one_with_its_text(store: Store):
    art = store.artifacts.create(
        "Kịch bản", "code", "default", AGENT, "c1", "print(1)\n", language="python", source="a.py"
    )
    assert (art.title, art.kind, art.language, art.agent_id) == (
        "Kịch bản",
        "code",
        "python",
        "default",
    )
    assert (art.head_version, art.source) == (1, "a.py")
    assert store.artifacts.get(art.id) == art

    head = store.artifacts.head(art.id)
    assert (head.version, head.author, head.conversation_id, head.note) == (1, AGENT, "c1", "")
    assert (head.content, head.data, head.size) == ("print(1)\n", None, 9)


def test_size_counts_the_bytes_of_the_utf8_text(store: Store):
    art = _create(store, content="đ")
    assert store.artifacts.head(art.id).size == 2


def test_an_image_keeps_its_bytes_and_no_text(store: Store):
    art = store.artifacts.create("Logo", "image", "default", AGENT, "c1", data=PNG)
    head = store.artifacts.head(art.id)
    assert (head.data, head.content, head.size) == (PNG, None, len(PNG))


@pytest.mark.parametrize("junk", [b"<svg onload='x'/>", b"\x89PNG", b"RIFF\x00\x00\x00\x00WAVE"])
def test_bytes_that_are_no_picture_are_stored_on_no_path(store: Store, junk: bytes):
    """Create and write go through the one check, so a picture canvas never holds bytes a
    browser would be asked to draw as something else. A restore only writes again a version
    that passed it."""
    with pytest.raises(NotAnImage):
        store.artifacts.create("Logo", "image", "default", AGENT, "c1", data=junk)
    assert store.artifacts.list() == []
    art = store.artifacts.create("Logo", "image", "default", AGENT, "c1", data=PNG)
    with pytest.raises(NotAnImage):
        store.artifacts.write(art.id, None, AGENT, "c1", data=junk)
    assert [v.version for v in store.artifacts.versions(art.id)] == [1]
    assert store.artifacts.head(art.id).data == PNG


@pytest.mark.parametrize(
    ("kind", "content", "data"),
    [
        ("markdown", None, None),
        ("markdown", "a", b"a"),
        ("code", None, b"a"),
        ("image", "a", None),
        ("image", None, None),
    ],
)
def test_a_payload_that_does_not_fit_the_kind_stores_nothing(store: Store, kind, content, data):
    with pytest.raises(PayloadMismatch):
        store.artifacts.create("t", kind, "default", AGENT, "c1", content, data)
    assert store.artifacts.list() == []


def test_an_unknown_kind_stores_nothing(store: Store):
    with pytest.raises(UnknownKind):
        store.artifacts.create("t", "pdf", "default", AGENT, "c1", "x")
    assert store.artifacts.list() == []


def test_a_version_over_its_kinds_cap_is_refused_on_create_and_on_write(store: Store):
    cap = cap_bytes("markdown")
    with pytest.raises(ArtifactTooLarge):
        _create(store, content="x" * (cap + 1))
    art = _create(store, content="x" * cap)
    with pytest.raises(ArtifactTooLarge):
        store.artifacts.write(art.id, "y" * (cap + 1), AGENT, "c1")
    assert [v.version for v in store.artifacts.versions(art.id)] == [1]
    with pytest.raises(ArtifactTooLarge):
        store.artifacts.create(
            "t", "image", "default", AGENT, "", data=bytes(cap_bytes("image") + 1)
        )


def test_the_cap_is_measured_on_the_text_as_stored(store: Store):
    """Line breaks become LF first, so a document is not refused for CRLFs a browser would
    never have sent back."""
    cap = cap_bytes("markdown")
    art = _create(store, content="x\r\n" * (cap // 2))
    assert store.artifacts.head(art.id).size == cap


def test_what_does_not_exist_raises_key_error(store: Store):
    calls = [
        lambda: store.artifacts.get("nope"),
        lambda: store.artifacts.head("nope"),
        lambda: store.artifacts.version("nope", 1),
        lambda: store.artifacts.versions("nope"),
        lambda: store.artifacts.write("nope", "x", AGENT, "c1"),
        lambda: store.artifacts.apply("nope", lambda head: head.content.upper(), AGENT, "c1"),
        lambda: store.artifacts.restore("nope", 1, USER, "c1"),
        lambda: store.artifacts.rename("nope", "x"),
        lambda: store.artifacts.delete("nope"),
    ]
    for call in calls:
        with pytest.raises(KeyError) as caught:
            call()
        assert not isinstance(caught.value, VersionGone)


def test_a_version_gone_from_a_canvas_that_is_there_names_the_newest(store: Store, canvas_clock):
    """Folded into the next save, or never written: either way the reader should move on
    to the newest version rather than give the canvas up."""
    art = _create(store, agent_id="", author=USER)
    canvas_clock.tick(1)
    store.artifacts.write(art.id, "# b", USER, "c1")
    for call in (
        lambda: store.artifacts.version(art.id, 1),
        lambda: store.artifacts.version(art.id, 9),
        lambda: store.artifacts.restore(art.id, 1, USER, "c1"),
    ):
        with pytest.raises(VersionGone) as caught:
            call()
        assert (caught.value.artifact_id, caught.value.head_version) == (art.id, 2)
    assert caught.value.version == 1
    assert isinstance(caught.value, KeyError)
    assert [v.version for v in store.artifacts.versions(art.id)] == [2]


def test_versions_lists_the_history_without_the_payloads(store: Store):
    art = _create(store, content="# a")
    store.artifacts.write(art.id, "# bb", AGENT, "c1")
    history = store.artifacts.versions(art.id)
    assert [(v.version, v.size, v.content, v.data) for v in history] == [
        (1, 3, None, None),
        (2, 4, None, None),
    ]


def test_a_write_can_retitle_the_canvas_and_otherwise_keeps_its_title(store: Store):
    art = _create(store, title="Cũ")
    store.artifacts.write(art.id, "# b", AGENT, "c1")
    assert store.artifacts.get(art.id).title == "Cũ"
    store.artifacts.write(art.id, "# c", AGENT, "c1", title="Mới")
    assert (store.artifacts.get(art.id).title, store.artifacts.get(art.id).head_version) == (
        "Mới",
        3,
    )


def test_rename_changes_the_title_without_a_new_version(store: Store, canvas_clock):
    art = _create(store)
    canvas_clock.tick(5)
    renamed = store.artifacts.rename(art.id, "Tên mới")
    assert (renamed.title, renamed.head_version, renamed.updated_at) == (
        "Tên mới",
        1,
        canvas_clock.now,
    )
    assert store.artifacts.get(art.id) == renamed
    assert [v.version for v in store.artifacts.versions(art.id)] == [1]


def test_delete_drops_versions_links_and_focus_and_leaves_other_canvases_alone(store: Store):
    links = store.artifact_links
    first, second = store.create().id, store.create().id
    art, other = _create(store), _create(store, title="Khác")
    store.artifacts.write(art.id, "# b", AGENT, "c1")
    links.mark_seen(first, art.id, 1)
    links.mark_seen(first, other.id, 1)
    links.set_focus(first, art.id, None)
    links.set_focus(second, other.id, None)

    store.artifacts.delete(art.id)

    with pytest.raises(KeyError):
        store.artifacts.get(art.id)
    left = store._conn.execute(
        "SELECT COUNT(*) FROM artifact_versions WHERE artifact_id = ?", (art.id,)
    )
    assert left.fetchone()[0] == 0
    assert [link.artifact_id for link in links.links_for(first)] == [other.id]
    assert links.focus(first) is None
    assert links.focus(second).artifact_id == other.id
    assert store.artifacts.sizes() == {other.id: 3}


def test_list_puts_the_most_recently_changed_canvas_first(store: Store, canvas_clock):
    older = _create(store, title="A")
    canvas_clock.tick(1)
    _create(store, title="B")
    canvas_clock.tick(1)
    store.artifacts.write(older.id, "# a2", AGENT, "c1")
    assert _titles(store.artifacts.list()) == ["A", "B"]


def test_list_breaks_a_tie_within_one_second_by_creation_order(store: Store, canvas_clock):
    _create(store, title="A")
    _create(store, title="B")
    assert _titles(store.artifacts.list()) == ["B", "A"]


def test_list_filters_by_conversation_and_by_agent(store: Store):
    first, second, third = store.create().id, store.create().id, store.create().id
    mine = _create(store, title="Của default")
    coach = _create(store, title="Của coach", agent_id="coach", author="agent:coach")
    person = _create(store, title="Của người", agent_id="", author=USER)
    store.artifact_links.link(first, mine.id)
    store.artifact_links.link(first, person.id)
    store.artifact_links.link(second, coach.id)

    assert _titles(store.artifacts.list(conversation_id=first)) == ["Của người", "Của default"]
    assert _titles(store.artifacts.list(agent_id="coach")) == ["Của coach"]
    assert _titles(store.artifacts.list(conversation_id=first, agent_id="")) == ["Của người"]
    assert store.artifacts.list(conversation_id=third) == []


def test_list_matches_the_title_regardless_of_case_and_accents(store: Store):
    _create(store, title="Kế hoạch tập luyện")
    _create(store, title="Ngân sách")
    for query in ("kế hoạch", "KẾ HOẠCH", "ke hoach", "TẬP", "  luyện "):
        assert _titles(store.artifacts.list(query=query)) == ["Kế hoạch tập luyện"]
    assert store.artifacts.list(query="đường") == []


def test_list_stops_at_the_limit(store: Store):
    for n in range(5):
        _create(store, title=f"t{n}")
    assert _titles(store.artifacts.list(limit=2)) == ["t4", "t3"]
    assert _titles(store.artifacts.list(query="T", limit=2)) == ["t4", "t3"]


def test_sizes_add_up_every_version_of_each_canvas(store: Store):
    text = _create(store, content="# a")
    store.artifacts.write(text.id, "# bb", AGENT, "c1")
    image = store.artifacts.create("Logo", "image", "default", AGENT, "c1", data=PNG)
    assert store.artifacts.sizes() == {text.id: 7, image.id: len(PNG)}


def test_on_change_hears_every_write_after_commit_outside_the_lock(store: Store):
    heard: list[tuple] = []

    def on_change(summary: dict, conversation_ids: list[str]) -> None:
        free = lock_is_free(store)
        heard.append((summary, conversation_ids, store._conn.in_transaction, free))

    store.artifacts.on_change = on_change
    first, second = store.create().id, store.create().id
    art = _create(store, content="# a")
    store.artifact_links.link(first, art.id)
    store.artifact_links.link(second, art.id)
    store.artifacts.write(art.id, "# b", AGENT, "c1")
    store.artifacts.apply(art.id, lambda head: head.content.upper(), AGENT, "c1")
    store.artifacts.restore(art.id, 1, USER, "c1")
    store.artifacts.rename(art.id, "Mới")
    store.artifacts.delete(art.id)

    linked = [first, second]
    assert [(s.get("head_version"), ids) for s, ids, _, _ in heard] == [
        (1, []),
        (2, linked),
        (3, linked),
        (4, linked),
        (4, linked),
        (None, linked),
    ]
    assert heard[4][0]["title"] == "Mới"
    assert heard[-1][0] == {"id": art.id, "deleted": True}
    assert all(not in_transaction and free for _, _, in_transaction, free in heard)


def test_a_failing_on_change_is_logged_and_the_write_stands(store: Store, caplog):
    def broken(summary: dict, conversation_ids: list[str]) -> None:
        raise RuntimeError("hub is gone")

    store.artifacts.on_change = broken
    with caplog.at_level(logging.ERROR, logger="my_agent_crew.store.artifacts"):
        art = _create(store)
        version = store.artifacts.write(art.id, "# b", AGENT, "c1")

    assert version.version == 2
    assert store.artifacts.head(art.id).content == "# b"
    assert "hub is gone" in caplog.text
