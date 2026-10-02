"""A canvas's history over REST: its versions newest first, one version whole, a restore that
writes an old version as the newest, and the raw text, which the browser is only ever given as
plain text, under the canvas's title as a file name when it is downloaded."""

from __future__ import annotations

import re
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.server import create_app
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store
from tests.canvas_helpers import PLAN, SWIM, agents_canvas

SANDBOX = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
DISPOSITION = re.compile(
    r"(inline|attachment); filename=\"([a-z0-9._-]+)\"; filename\*=UTF-8''(.+)"
)


@pytest.fixture
def client(deps_factory):
    app = create_app(deps_factory(), schedule=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client


def _written_twice(store: Store) -> str:
    """The coach's canvas at version 3: PLAN, then SWIM, then a third line."""
    art = agents_canvas(store, "coach", PLAN)
    store.artifacts.write(art, SWIM, "agent:coach", "")
    store.artifacts.write(art, SWIM + "ngủ sớm\n", "agent:coach", "")
    return art


def test_the_versions_are_listed_newest_first_without_their_text(client, store: Store):
    art = _written_twice(store)
    listed = client.get(f"/api/artifacts/{art}/versions").json()
    assert listed == [version.meta() for version in reversed(store.artifacts.versions(art))]
    assert [version["version"] for version in listed] == [3, 2, 1]
    assert all("content" not in version for version in listed)


def test_one_version_comes_whole(client, store: Store):
    art = _written_twice(store)
    response = client.get(f"/api/artifacts/{art}/versions/2")
    assert response.status_code == 200
    assert response.json() == {**store.artifacts.version(art, 2).meta(), "content": SWIM}


def test_a_version_folded_away_is_404_with_the_newest_number(client, store: Store, canvas_clock):
    art = agents_canvas(store, "coach", PLAN)
    store.artifacts.write(art, SWIM, USER, "")
    store.artifacts.write(art, SWIM + "x\n", USER, "")  # folds version 2 into 3
    for response in (
        client.get(f"/api/artifacts/{art}/versions/2"),
        client.get(f"/api/artifacts/{art}/raw", params={"version": 2}),
        client.post(f"/api/artifacts/{art}/restore", json={"version": 2}),
    ):
        assert (response.status_code, response.json()["detail"]) == (404, {"head_version": 3})
    assert store.artifacts.head(art).version == 3


def test_a_missing_canvas_is_404_to_every_history_route(client):
    for response in (
        client.get("/api/artifacts/nope/versions"),
        client.get("/api/artifacts/nope/versions/1"),
        client.post("/api/artifacts/nope/restore", json={"version": 1}),
        client.get("/api/artifacts/nope/raw"),
    ):
        assert (response.status_code, response.json()["detail"]) == (404, "artifact not found")


def test_a_restore_writes_the_old_version_as_the_persons_newest(client, store: Store):
    art = _written_twice(store)
    response = client.post(f"/api/artifacts/{art}/restore", json={"version": 1})
    assert response.status_code == 200
    head = store.artifacts.head(art)
    assert response.json() == head.meta()
    assert (head.version, head.content, head.note) == (4, PLAN, "restore:1")
    assert (head.author, head.conversation_id) == (USER, "")


@pytest.mark.parametrize("version", [True, 0, "1", None])
def test_a_restore_names_a_real_version_number(client, store: Store, version):
    art = _written_twice(store)
    response = client.post(f"/api/artifacts/{art}/restore", json={"version": version})
    assert response.status_code == 422
    assert store.artifacts.head(art).version == 3


def test_the_raw_text_is_plain_text_that_runs_nothing(client, store: Store):
    art = agents_canvas(store, "coach", "<script>fetch('/api/settings')</script>")
    response = client.get(f"/api/artifacts/{art}/raw")
    assert response.status_code == 200
    assert response.text == "<script>fetch('/api/settings')</script>"
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    assert response.headers["content-security-policy"] == SANDBOX
    assert response.headers["content-disposition"].startswith("inline;")


def test_the_raw_text_of_an_older_version(client, store: Store):
    art = _written_twice(store)
    assert client.get(f"/api/artifacts/{art}/raw", params={"version": 1}).text == PLAN
    assert client.get(f"/api/artifacts/{art}/raw").text == SWIM + "ngủ sớm\n"


@pytest.mark.parametrize(
    ("kind", "language", "name", "plain"),
    [
        ("markdown", "", "Kế hoạch tuần.md", "ke-hoach-tuan.md"),
        ("code", "python", "Kế hoạch tuần.py", "ke-hoach-tuan.py"),
        ("code", "", "Kế hoạch tuần.txt", "ke-hoach-tuan.txt"),
    ],
)
def test_a_download_is_named_after_the_title_in_any_script(
    client, store: Store, kind, language, name, plain
):
    created = store.artifacts.create("Kế hoạch tuần", kind, "", USER, "", "x", language=language)
    response = client.get(f"/api/artifacts/{created.id}/raw", params={"download": 1})
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["content-security-policy"] == SANDBOX
    header = response.headers["content-disposition"]
    match = DISPOSITION.fullmatch(header)
    assert match, header
    assert (match[1], match[2], unquote(match[3])) == ("attachment", plain, name)
