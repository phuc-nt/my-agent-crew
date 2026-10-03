"""A canvas's history over REST: its versions newest first, one version whole, a restore that
writes an old version as the newest, and the raw payload. The browser is given text as plain text
whatever the kind, a drawing as an image it draws without running, and a picture as its own bytes
under the type they give, always sandboxed. A download is named after the canvas's title."""

from __future__ import annotations

import re
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.server import create_app
from my_agent_crew.server.security_headers import FRAME_ANCESTORS
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store
from tests.canvas_helpers import PLAN, SWIM, agents_canvas

SANDBOX = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
DISPOSITION = re.compile(
    r"(inline|attachment); filename=\"([a-z0-9._-]+)\"; filename\*=UTF-8''(.+)"
)
TEXT = "text/plain; charset=utf-8"
PICTURES = [
    (".png", b"\x89PNG\r\n\x1a\n" + bytes(range(32)), "image/png"),
    (".jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF" + bytes(range(32)), "image/jpeg"),
    (".gif", b"GIF89a" + bytes(range(32)), "image/gif"),
    (".webp", b"RIFF\x1a\x00\x00\x00WEBPVP8 " + bytes(range(32)), "image/webp"),
]


@pytest.fixture
def client(deps_factory):
    app = create_app(deps_factory(), schedule=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client


def _disposition(response) -> tuple[str, str, str]:
    header = response.headers["content-disposition"]
    match = DISPOSITION.fullmatch(header)
    assert match, header
    return match[1], match[2], unquote(match[3])


def _contained(response) -> None:
    """What every `/raw` answer carries whatever it holds."""
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    assert response.headers.get_list("content-security-policy") == [SANDBOX, FRAME_ANCESTORS]


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
    assert response.headers.get_list("content-security-policy") == [SANDBOX, FRAME_ANCESTORS]
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
        ("code", "html", "Kế hoạch tuần.html.txt", "ke-hoach-tuan.html.txt"),
        ("code", "", "Kế hoạch tuần.txt", "ke-hoach-tuan.txt"),
        ("html", "", "Kế hoạch tuần.html.txt", "ke-hoach-tuan.html.txt"),
        ("svg", "", "Kế hoạch tuần.svg.txt", "ke-hoach-tuan.svg.txt"),
        ("mermaid", "", "Kế hoạch tuần.mmd", "ke-hoach-tuan.mmd"),
    ],
)
def test_a_download_is_named_after_the_title_in_any_script(
    client, store: Store, kind, language, name, plain
):
    created = store.artifacts.create("Kế hoạch tuần", kind, "", USER, "", "x", language=language)
    response = client.get(f"/api/artifacts/{created.id}/raw", params={"download": 1})
    assert response.headers["content-type"] == TEXT
    assert response.headers.get_list("content-security-policy") == [SANDBOX, FRAME_ANCESTORS]
    assert _disposition(response) == ("attachment", plain, name)


def test_a_page_is_shown_and_saved_as_text_and_never_as_a_page(client, store: Store):
    page = "<!doctype html><script>fetch('/api/settings')</script>"
    art = store.artifacts.create("Kế hoạch tuần", "html", "", USER, "", page).id
    shown = client.get(f"/api/artifacts/{art}/raw")
    assert (shown.status_code, shown.text, shown.headers["content-type"]) == (200, page, TEXT)
    assert _disposition(shown)[0] == "inline"
    _contained(shown)
    saved = client.get(f"/api/artifacts/{art}/raw", params={"download": 1})
    assert (saved.text, saved.headers["content-type"]) == (page, TEXT)
    assert _disposition(saved) == ("attachment", "ke-hoach-tuan.html.txt", "Kế hoạch tuần.html.txt")
    _contained(saved)


def test_a_drawing_is_shown_as_an_image_that_downloads_and_is_saved_as_text(client, store: Store):
    """An `<img>` draws an SVG without running its script and ignores the disposition of the
    answer, so the panel still shows it. Opened as a document the answer downloads instead, and
    under a name a browser will not run from the disk."""
    svg = '<svg xmlns="http://www.w3.org/2000/svg" onload="fetch(\'/api/settings\')"/>'
    art = store.artifacts.create("Sơ đồ", "svg", "", USER, "", svg).id
    shown = client.get(f"/api/artifacts/{art}/raw")
    assert (shown.status_code, shown.text) == (200, svg)
    assert shown.headers["content-type"] == "image/svg+xml"
    assert _disposition(shown) == ("attachment", "so-do.svg.txt", "Sơ đồ.svg.txt")
    _contained(shown)
    saved = client.get(f"/api/artifacts/{art}/raw", params={"download": 1})
    assert (saved.text, saved.headers["content-type"]) == (svg, TEXT)
    assert _disposition(saved) == ("attachment", "so-do.svg.txt", "Sơ đồ.svg.txt")
    _contained(saved)


def test_a_diagram_is_text_whether_it_is_shown_or_saved(client, store: Store):
    art = store.artifacts.create("Luồng", "mermaid", "", USER, "", "graph TD\n  A --> B\n").id
    for params, disposition in (({}, "inline"), ({"download": 1}, "attachment")):
        response = client.get(f"/api/artifacts/{art}/raw", params=params)
        assert response.text == "graph TD\n  A --> B\n"
        assert response.headers["content-type"] == TEXT
        assert _disposition(response) == (disposition, "luong.mmd", "Luồng.mmd")
        _contained(response)


@pytest.mark.parametrize(("extension", "data", "media_type"), PICTURES)
def test_a_picture_goes_out_as_its_own_bytes_under_the_type_they_give(
    client, store: Store, extension, data, media_type
):
    art = store.artifacts.create("Ảnh bìa", "image", "", USER, "", data=data).id
    assert client.get(f"/api/artifacts/{art}").json()["content"] is None
    shown = client.get(f"/api/artifacts/{art}/raw")
    assert (shown.status_code, shown.content) == (200, data)
    assert shown.headers["content-type"] == media_type
    assert _disposition(shown) == ("inline", "anh-bia" + extension, "Ảnh bìa" + extension)
    _contained(shown)
    saved = client.get(f"/api/artifacts/{art}/raw", params={"download": 1})
    assert (saved.content, saved.headers["content-type"]) == (data, media_type)
    assert _disposition(saved) == ("attachment", "anh-bia" + extension, "Ảnh bìa" + extension)
    _contained(saved)


def test_an_older_version_of_a_picture_comes_with_its_own_bytes_and_type(client, store: Store):
    (_, png, _), (_, jpeg, _) = PICTURES[0], PICTURES[1]
    art = store.artifacts.create("Ảnh", "image", "", USER, "", data=png).id
    store.artifacts.write(art, None, "agent:coach", "", data=jpeg)
    older = client.get(f"/api/artifacts/{art}/raw", params={"version": 1})
    assert (older.content, older.headers["content-type"]) == (png, "image/png")
    newest = client.get(f"/api/artifacts/{art}/raw")
    assert (newest.content, newest.headers["content-type"]) == (jpeg, "image/jpeg")
    assert _disposition(newest)[2] == "Ảnh.jpg"
