"""Canvases over REST, as the web panel uses them: list, create, read, save, rename, delete.
Every write is the person's (`user`, from no conversation in particular), a save names the
version it was made on and never writes over a newer one, and every refusal of the store comes
back with its own status code and nothing stored."""

from __future__ import annotations

from typing import get_args

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.artifacts.kinds import CREATABLE_KINDS, cap_bytes
from my_agent_crew.server import create_app
from my_agent_crew.server.routes_artifacts import CreateBody
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store
from tests.canvas_helpers import PLAN, agents_canvas


@pytest.fixture
def client(deps_factory):
    app = create_app(deps_factory(), schedule=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client


def _create(client: TestClient, **body) -> dict:
    sent = {"title": "Kế hoạch", "kind": "markdown", **body}
    response = client.post("/api/artifacts", json=sent)
    assert response.status_code == 201, response.text
    return response.json()


def _save(client: TestClient, art: str, content: str, base_version):
    body = {"content": content, "base_version": base_version}
    return client.put(f"/api/artifacts/{art}", json=body)


def test_a_canvas_made_on_the_web_is_the_persons_and_reads_back_the_same(client, store: Store):
    made = _create(client, content=PLAN)
    assert made == client.get(f"/api/artifacts/{made['id']}").json()
    assert (made["agent_id"], made["head_author"], made["head_version"]) == ("", USER, 1)
    assert (made["content"], made["conversation_ids"], made["kind"]) == (PLAN, [], "markdown")
    assert store.artifacts.head(made["id"]).conversation_id == ""


def test_a_canvas_made_in_a_conversation_is_shared_with_it_and_open_there(client, store: Store):
    conv = store.create()
    made = _create(client, conversation_id=conv.id)
    link = store.artifact_links.get(conv.id, made["id"])
    assert (link.shared, link.seen_version, link.noted_version) == (True, 0, 0)
    focus = store.artifact_links.focus(conv.id)
    assert (focus.artifact_id, focus.selection) == (made["id"], None)
    assert made["conversation_ids"] == [conv.id]


def test_a_canvas_for_a_missing_conversation_is_404_and_nothing_is_made(
    client, store: Store, monkeypatch
):
    heard: list[dict] = []
    monkeypatch.setattr(store.artifacts, "on_change", lambda summary, _: heard.append(summary))
    sent = {"title": "Kế hoạch", "kind": "markdown", "conversation_id": "nope"}
    response = client.post("/api/artifacts", json=sent)
    assert (response.status_code, response.json()["detail"]) == (404, "conversation not found")
    assert (store.artifacts.list(), heard) == ([], [])


@pytest.mark.parametrize("kind", ["markdown", "code", "html", "svg", "mermaid"])
def test_the_web_makes_a_canvas_of_every_kind_that_is_text(client, store: Store, kind):
    made = _create(client, kind=kind, content="x")
    assert (made["kind"], made["content"]) == (kind, "x")
    assert made == client.get(f"/api/artifacts/{made['id']}").json()
    assert store.artifacts.head(made["id"]).content == "x"


@pytest.mark.parametrize("kind", ["image", "pdf", "", "HTML"])
def test_the_web_makes_no_canvas_of_a_kind_that_is_not_text(client, store: Store, kind):
    response = client.post("/api/artifacts", json={"title": "Kế hoạch", "kind": kind})
    assert response.status_code == 422
    assert store.artifacts.list() == []


def test_the_kinds_the_web_may_create_are_the_ones_the_store_lists():
    """`CreateBody.kind` is spelt out so the API schema names the kinds; this keeps it from
    drifting from the table the store and the tools read."""
    assert get_args(CreateBody.model_fields["kind"].annotation) == CREATABLE_KINDS


def test_a_page_may_be_far_larger_than_text_and_its_413_names_its_own_cap(client, store: Store):
    cap = cap_bytes("html")
    made = _create(client, kind="html", content="x" * cap)
    assert store.artifacts.head(made["id"]).size == cap
    over = {"title": "Trang", "kind": "html", "content": "x" * (cap + 1)}
    refused = client.post("/api/artifacts", json=over)
    assert (refused.status_code, refused.json()["detail"]) == (413, {"size": cap + 1, "cap": cap})
    assert _save(client, made["id"], "y" * (cap + 1), 1).status_code == 413
    assert _save(client, made["id"], "y" * 1024, 1).status_code == 200
    assert [summary.id for summary in store.artifacts.list()] == [made["id"]]


@pytest.mark.parametrize(
    ("title", "detail"),
    [("   ", "a canvas needs a title"), ("x" * 201, "a title of 201 characters is over 200")],
)
def test_a_title_the_store_refuses_is_422_with_its_reason(client, store: Store, title, detail):
    response = client.post("/api/artifacts", json={"title": title, "kind": "markdown"})
    assert (response.status_code, response.json()["detail"]) == (422, detail)
    assert store.artifacts.list() == []


def test_a_version_over_its_kind_cap_is_413_and_nothing_is_written(client, store: Store):
    cap = cap_bytes("markdown")
    response = client.post(
        "/api/artifacts", json={"title": "Kế hoạch", "kind": "markdown", "content": "x" * (cap + 1)}
    )
    assert (response.status_code, response.json()["detail"]) == (413, {"size": cap + 1, "cap": cap})
    assert store.artifacts.list() == []
    art = _create(client, content="# a")["id"]
    assert _save(client, art, "x" * (cap + 1), 1).status_code == 413
    assert store.artifacts.head(art).content == "# a"


def test_full_storage_is_507_naming_the_largest_canvases(client, store: Store, monkeypatch):
    first = _create(client, content="x" * 40)
    monkeypatch.setattr("my_agent_crew.store.artifacts.STORAGE_CAP", 50)
    sent = {"title": "Thêm", "kind": "markdown", "content": "y" * 20}
    response = client.post("/api/artifacts", json=sent)
    assert response.status_code == 507
    largest = [{"id": first["id"], "title": "Kế hoạch", "size": 40}]
    assert response.json()["detail"] == {"used": 40, "cap": 50, "largest": largest}
    assert [summary.id for summary in store.artifacts.list()] == [first["id"]]


def test_the_detail_is_one_version_whole_though_a_write_lands_between_its_reads(
    client, store: Store, monkeypatch
):
    """Whichever of the summary and the newest version the route reads first, an agent's write
    lands right after it; the content, author and number shown still belong together."""
    arts = store.artifacts
    art = agents_canvas(store, "coach", "# a")
    landed: list[int] = []

    def then_write(read):
        def wrapped(artifact_id: str):
            result = read(artifact_id)
            if not landed:
                landed.append(1)  # first, so the write's own reads go straight through
                arts.write(art, "# written meanwhile", "agent:coach", "")
            return result

        return wrapped

    monkeypatch.setattr(arts, "get", then_write(arts.get))
    monkeypatch.setattr(arts, "head", then_write(arts.head))
    shown = client.get(f"/api/artifacts/{art}").json()
    assert landed
    version = arts.version(art, shown["head_version"])
    assert (shown["content"], shown["head_author"]) == (version.content, version.author)


def test_a_missing_canvas_is_404_to_every_route(client):
    for response in (
        client.get("/api/artifacts/nope"),
        _save(client, "nope", "x", 1),
        client.patch("/api/artifacts/nope", json={"title": "Mới"}),
        client.delete("/api/artifacts/nope"),
    ):
        assert (response.status_code, response.json()["detail"]) == (404, "artifact not found")


@pytest.mark.parametrize(
    "body",
    [
        {"content": "# b"},
        {"content": "# b", "base_version": True},
        {"content": "# b", "base_version": 0},
        {"content": "# b", "base_version": "1"},
        {"content": "# b", "base_version": None},
    ],
    ids=["missing", "true", "zero", "string", "null"],
)
def test_a_save_without_a_real_base_version_is_422_and_writes_nothing(client, store: Store, body):
    art = _create(client, content="# a")["id"]
    response = client.put(f"/api/artifacts/{art}", json=body)
    assert response.status_code == 422
    assert (store.artifacts.head(art).version, store.artifacts.head(art).content) == (1, "# a")


def test_a_save_on_the_newest_version_writes_the_persons_version(client, store: Store):
    art = agents_canvas(store, "coach", "# a")
    response = _save(client, art, "# b", 1)
    assert response.status_code == 200
    head = store.artifacts.head(art)
    assert response.json() == head.meta()
    assert (head.version, head.content, head.author, head.conversation_id) == (2, "# b", USER, "")


def test_a_save_on_a_stale_version_is_409_with_the_newest_and_writes_nothing(client, store: Store):
    art = agents_canvas(store, "coach", "# a")
    store.artifacts.write(art, "# theirs", "agent:coach", "")
    response = _save(client, art, "# mine", 1)
    assert response.status_code == 409
    newest = {"head_version": 2, "content": "# theirs", "author": "agent:coach"}
    assert response.json()["detail"] == newest
    assert store.artifacts.head(art).content == "# theirs"


def test_saves_in_one_burst_fold_together_and_still_count_up(client, store: Store, canvas_clock):
    art = _create(client, content="# a")["id"]
    first = _save(client, art, "# b", 1).json()
    canvas_clock.tick(5)
    second = _save(client, art, "# c", first["version"]).json()
    assert (first["version"], second["version"]) == (2, 3)
    assert [version.version for version in store.artifacts.versions(art)] == [3]
    assert _save(client, art, "# d", 2).status_code == 409


def test_a_rename_changes_the_title_and_writes_no_version(client, store: Store):
    art = _create(client, content="# a")["id"]
    response = client.patch(f"/api/artifacts/{art}", json={"title": "  Kế hoạch\nmới "})
    assert response.status_code == 200
    assert response.json() == store.artifacts.get(art).to_dict()
    assert (response.json()["title"], response.json()["head_version"]) == ("Kế hoạch mới", 1)
    assert len(store.artifacts.versions(art)) == 1
    blank = client.patch(f"/api/artifacts/{art}", json={"title": " "})
    assert (blank.status_code, blank.json()["detail"]) == (422, "a canvas needs a title")


def test_a_deleted_canvas_is_gone(client, store: Store):
    conv = store.create()
    art = _create(client, conversation_id=conv.id)["id"]
    response = client.delete(f"/api/artifacts/{art}")
    assert (response.status_code, response.content) == (204, b"")
    assert client.get(f"/api/artifacts/{art}").status_code == 404
    assert store.artifact_links.focus(conv.id) is None
    assert store.get(conv.id).id == conv.id


def test_the_list_is_newest_first_and_filters_by_conversation_and_title(client, store: Store):
    conv = store.create()
    older = _create(client, title="Kế hoạch bơi")["id"]
    newer = _create(client, title="Thực đơn", conversation_id=conv.id)["id"]
    listed = client.get("/api/artifacts").json()
    assert [summary["id"] for summary in listed] == [newer, older]
    assert listed[0] == store.artifacts.get(newer).to_dict()
    by_conversation = client.get("/api/artifacts", params={"conversation_id": conv.id}).json()
    assert [summary["id"] for summary in by_conversation] == [newer]
    assert client.get("/api/artifacts", params={"conversation_id": "nope"}).json() == []
    found = client.get("/api/artifacts", params={"q": "KE HOACH"}).json()
    assert [summary["id"] for summary in found] == [older]
    assert len(client.get("/api/artifacts", params={"limit": 1}).json()) == 1


@pytest.mark.parametrize("limit", [0, 201, -1])
def test_the_list_limit_stays_between_1_and_200(client, limit):
    assert client.get("/api/artifacts", params={"limit": limit}).status_code == 422
