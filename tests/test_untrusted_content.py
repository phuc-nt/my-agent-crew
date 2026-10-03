"""Files an agent wrote, served to the browser as untrusted content. Only raster images, PDF and
plain text may open in place; everything else downloads as bytes, and nothing opens as a page
of the app. The table is pinned in code, so these headers are the same on every machine."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.server import create_app
from my_agent_crew.server.security_headers import FRAME_ANCESTORS
from my_agent_crew.server.untrusted_content import BYTES, Shown, canvas_shown, disposition

# No `allow-scripts`, no `allow-same-origin`: a page opened from here runs no script and has
# an opaque origin, whose requests the local guard refuses. The rule against framing the app
# goes out after it, as a second policy on every response.
SANDBOX = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
TEXT = "text/plain; charset=utf-8"
HEADER = re.compile(
    r"(inline|attachment); filename=\"([a-z0-9._-]+)\"; filename\*=UTF-8''([A-Za-z0-9%._~-]+)"
)


@pytest.fixture
def served(deps_factory):
    deps = deps_factory()
    with TestClient(create_app(deps, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, deps.agent.workspace


def _get(served: tuple[TestClient, Path], name: str, body: bytes = b"x"):
    client, workspace = served
    (workspace / name).write_bytes(body)
    response = client.get("/api/agents/default/files", params={"path": name})
    assert response.status_code == 200
    assert response.content == body
    return response


@pytest.mark.parametrize(
    ("name", "media_type"),
    [
        ("sleep.png", "image/png"),
        ("SLEEP.PNG", "image/png"),
        ("photo.jpg", "image/jpeg"),
        ("photo.JPEG", "image/jpeg"),
        ("loop.gif", "image/gif"),
        ("chart.webp", "image/webp"),
        ("chart.avif", "image/avif"),
        ("notes.txt", TEXT),
        ("run.log", TEXT),
    ],
)
def test_raster_images_and_plain_text_open_in_place_inside_a_sandbox(served, name, media_type):
    response = _get(served, name)
    assert response.headers["content-type"] == media_type
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers.get_list("content-security-policy") == [SANDBOX, FRAME_ANCESTORS]


@pytest.mark.parametrize(
    "name",
    [
        "page.html",
        "page.HTM",
        "page.xhtml",
        "page.xht",
        "feed.rss",
        "feed.atom",
        "style.xsl",
        "graph.rdf",
        "app.ts",
        "app.js",
        "app.mjs",
        "data.json",
        "data.xml",
        "style.css",
        "run.sh",
        "Makefile",
    ],
)
def test_every_other_file_downloads_as_bytes(served, name):
    response = _get(served, name, b"<script>fetch('/api/settings')</script>")
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers.get_list("content-security-policy") == [SANDBOX, FRAME_ANCESTORS]


def test_an_svg_downloads_when_opened_and_still_shows_in_an_img(served):
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"
    response = _get(served, "chart.svg", svg)
    assert response.headers["content-type"] == "image/svg+xml"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers.get_list("content-security-policy") == [SANDBOX, FRAME_ANCESTORS]


def test_a_pdf_opens_in_place_without_the_sandbox_its_viewer_cannot_run_in(served):
    response = _get(served, "report.pdf", b"%PDF-1.4")
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers.get_list("content-security-policy") == [FRAME_ANCESTORS]


@pytest.mark.parametrize("name", ["a.png", "a.svg", "a.pdf", "a.txt", "a.html", "a"])
def test_no_file_is_sniffed_or_read_from_another_origin(served, name):
    response = _get(served, name)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"


def test_a_file_named_in_any_script_is_served_under_its_own_name(served):
    response = _get(served, "メモ của tôi.html")
    match = HEADER.fullmatch(response.headers["content-disposition"])
    assert match, response.headers["content-disposition"]
    assert match[2] == "cua-toi.html"
    assert unquote(match[3]) == "メモ của tôi.html"


@pytest.mark.parametrize(
    ("name", "plain"),
    [
        ("Tiếng Việt.html", "tieng-viet.html"),
        ("Đọc sách.md", "doc-sach.md"),
        ("日本.md", "file.md"),
        ("メモ.html", "file.html"),
        ('a"b;c.html', "a-b-c.html"),
        ("line\nbreak\r.txt", "line-break.txt"),
        ("cœur", "c-ur"),
        ("🎉🎉", "file"),
        ("report.PDF", "report.pdf"),
        ("archive.tar.gz", "archive.tar.gz"),
        ("notes/2026.txt", "notes-2026.txt"),
    ],
)
def test_a_name_reaches_the_browser_whole_with_a_plain_fallback(name, plain):
    header = disposition(name, "file")
    header.encode("latin-1")  # a header value must encode as latin-1, or the route fails
    match = HEADER.fullmatch(header)
    assert match, header
    assert match[1] == "attachment"
    assert match[2] == plain
    assert unquote(match[3]) == name


def test_a_name_that_folds_to_nothing_takes_the_fallback_it_is_given():
    assert HEADER.fullmatch(disposition("メモ.md", "canvas"))[2] == "canvas.md"
    assert disposition("a.txt", "file", inline=True).startswith("inline;")


@pytest.mark.parametrize("kind", ["markdown", "code", "html", "mermaid"])
def test_a_canvas_of_text_goes_out_as_plain_text_that_downloads_on_request(kind):
    assert canvas_shown(kind, None, download=False) == Shown(TEXT, True, True)
    assert canvas_shown(kind, None, download=True) == Shown(TEXT, False, True)


def test_a_drawing_is_an_image_that_downloads_when_opened_and_text_when_saved():
    assert canvas_shown("svg", None, download=False) == Shown("image/svg+xml", False, True)
    assert canvas_shown("svg", None, download=True) == Shown(TEXT, False, True)


@pytest.mark.parametrize(
    ("data", "media_type"),
    [
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff\xe0", "image/jpeg"),
        (b"GIF89a", "image/gif"),
        (b"RIFF\x00\x00\x00\x00WEBP", "image/webp"),
    ],
)
def test_a_picture_goes_out_under_the_type_its_bytes_give(data, media_type):
    assert canvas_shown("image", data, download=False) == Shown(media_type, True, True)
    assert canvas_shown("image", data, download=True) == Shown(media_type, False, True)


@pytest.mark.parametrize("data", [b"<svg onload='x'/>", b"\x89PNG", b"", None])
@pytest.mark.parametrize("download", [False, True])
def test_bytes_of_no_type_we_know_go_out_as_bytes_that_never_open(data, download):
    shown = canvas_shown("image", data, download=download)
    assert shown == BYTES == Shown("application/octet-stream", False, True)
