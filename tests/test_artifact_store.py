"""Creating, reading, listing, renaming and deleting canvases, and the callback that tells the
rest of the app a canvas changed."""

import logging
import threading

import pytest

from my_agent_crew.artifacts.kinds import ArtifactTooLarge, PayloadMismatch, UnknownKind, cap_bytes
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store

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
    art = _create(store)
    calls = [
        lambda: store.artifacts.get("nope"),
        lambda: store.artifacts.head("nope"),
        lambda: store.artifacts.version(art.id, 9),
        lambda: store.artifacts.versions("nope"),
        lambda: store.artifacts.write("nope", "x", AGENT, "c1"),
        lambda: store.artifacts.apply("nope", str.upper, AGENT, "c1"),
        lambda: store.artifacts.restore(art.id, 9, USER, "c1"),
        lambda: store.artifacts.rename("nope", "x"),
        lambda: store.artifacts.delete("nope"),
    ]
    for call in calls:
        with pytest.raises(KeyError):
            call()


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
    art, other = _create(store), _create(store, title="Khác")
    store.artifacts.write(art.id, "# b", AGENT, "c1")
    links.mark_seen("c1", art.id, 1)
    links.mark_seen("c1", other.id, 1)
    links.set_focus("c1", art.id, None)
    links.set_focus("c2", other.id, None)

    store.artifacts.delete(art.id)

    with pytest.raises(KeyError):
        store.artifacts.get(art.id)
    left = store._conn.execute(
        "SELECT COUNT(*) FROM artifact_versions WHERE artifact_id = ?", (art.id,)
    )
    assert left.fetchone()[0] == 0
    assert [link.artifact_id for link in links.links_for("c1")] == [other.id]
    assert links.focus("c1") is None
    assert links.focus("c2").artifact_id == other.id
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
    mine = _create(store, title="Của default")
    coach = _create(store, title="Của coach", agent_id="coach")
    person = _create(store, title="Của người", agent_id="", author=USER)
    store.artifact_links.link("c1", mine.id)
    store.artifact_links.link("c1", person.id)
    store.artifact_links.link("c2", coach.id)

    assert _titles(store.artifacts.list(conversation_id="c1")) == ["Của người", "Của default"]
    assert _titles(store.artifacts.list(agent_id="coach")) == ["Của coach"]
    assert _titles(store.artifacts.list(conversation_id="c1", agent_id="")) == ["Của người"]
    assert store.artifacts.list(conversation_id="c3") == []


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


def _lock_is_free(store: Store) -> bool:
    """Whether another thread could take the store's lock right now."""
    taken: list[bool] = []

    def take() -> None:
        got = store._lock.acquire(timeout=1)
        taken.append(got)
        if got:
            store._lock.release()

    thread = threading.Thread(target=take)
    thread.start()
    thread.join()
    return taken[0]


def test_on_change_hears_every_write_after_commit_outside_the_lock(store: Store):
    heard: list[tuple] = []

    def on_change(summary: dict, conversation_ids: list[str]) -> None:
        free = _lock_is_free(store)
        heard.append((summary, conversation_ids, store._conn.in_transaction, free))

    store.artifacts.on_change = on_change
    art = _create(store, content="# a")
    store.artifact_links.link("c1", art.id)
    store.artifact_links.link("c2", art.id)
    store.artifacts.write(art.id, "# b", AGENT, "c1")
    store.artifacts.apply(art.id, str.upper, AGENT, "c1")
    store.artifacts.restore(art.id, 1, USER, "c1")
    store.artifacts.rename(art.id, "Mới")
    store.artifacts.delete(art.id)

    assert [(s.get("head_version"), ids) for s, ids, _, _ in heard] == [
        (1, []),
        (2, ["c1", "c2"]),
        (3, ["c1", "c2"]),
        (4, ["c1", "c2"]),
        (4, ["c1", "c2"]),
        (None, ["c1", "c2"]),
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
