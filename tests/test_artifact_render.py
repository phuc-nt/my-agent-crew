"""The page a canvas runs as, over REST: an html or a mermaid canvas comes back as a document under
a policy that lets it run and leaves it no way out, and no other canvas does. The policy is
written out here in full, so a change to it is a change to this file too."""

from __future__ import annotations

from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.artifacts.mermaid_page import MERMAID_URL, mermaid_page
from my_agent_crew.artifacts.render import html_page, render_csp
from my_agent_crew.server import create_app
from my_agent_crew.server.routes_artifact_render import NOT_A_PAGE
from my_agent_crew.server.security_headers import FRAME_ANCESTORS
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store

POLICY = (
    "sandbox allow-scripts; "
    "default-src 'none'; "
    "script-src 'unsafe-inline' 'unsafe-eval' https://cdnjs.cloudflare.com"
    " https://cdn.jsdelivr.net https://unpkg.com; "
    "style-src 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net"
    " https://unpkg.com https://fonts.googleapis.com; "
    "font-src data: https://fonts.gstatic.com https://cdnjs.cloudflare.com"
    " https://cdn.jsdelivr.net https://unpkg.com; "
    "img-src data: blob:; media-src data: blob:; connect-src 'none'; form-action 'none'; "
    "base-uri 'none'; frame-ancestors 'self'; webrtc 'block'"
)
# What the route decides, plus `content-length`. The gzip layer adds `vary` to any answer over its
# minimum size, compressed or not, and a page always is: it is no part of what the route sends.
HEADER_NAMES = {
    "cache-control",
    "content-length",
    "content-security-policy",
    "content-type",
    "referrer-policy",
    "x-content-type-options",
    "x-dns-prefetch-control",
}
PICTURE = b"\x89PNG\r\n\x1a\n" + bytes(range(32))


@pytest.fixture
def client(deps_factory):
    app = create_app(deps_factory(), schedule=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client


def _canvas(store: Store, kind: str, content: str, title: str = "Trang") -> str:
    return store.artifacts.create(title, kind, "coach", "agent:coach", "", content).id


def _directives(policy: str) -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {}
    for part in policy.split("; "):
        name, *sources = part.split(" ")
        assert name not in parsed, f"{name} twice: a browser keeps only the first"
        parsed[name] = sources
    return parsed


def test_the_policy_is_the_one_written_out_here():
    assert render_csp() == POLICY


def test_the_page_never_shares_the_apps_origin():
    # Scripts together with the app's origin let a page take its own sandbox off, and any other
    # token (popups, forms, top navigation, downloads) is a way out of it.
    assert _directives(render_csp())["sandbox"] == ["allow-scripts"]
    assert "allow-same-origin" not in render_csp()


def test_only_framing_names_the_apps_own_origin():
    named = [name for name, sources in _directives(render_csp()).items() if "'self'" in sources]
    assert named == ["frame-ancestors"]


def test_the_page_has_no_way_to_send_anything_out():
    parsed = _directives(render_csp())
    assert parsed["default-src"] == ["'none'"]
    for name in ("connect-src", "form-action", "base-uri"):
        assert parsed[name] == ["'none'"], name
    # An image or a media file asked for at an address carries what the page knows in it.
    for name in ("img-src", "media-src"):
        assert set(parsed[name]) <= {"data:", "blob:"}, name
    assert parsed["webrtc"] == ["'block'"]
    for name, sources in parsed.items():
        for source in sources:
            assert source not in {"*", "http:", "https:", "ws:", "wss:"}, name
            assert not source.startswith("http://"), name


def test_the_policy_lets_the_mermaid_page_load_its_library():
    host = urlsplit(MERMAID_URL)
    assert f"{host.scheme}://{host.netloc}" in _directives(render_csp())["script-src"]


def test_a_page_goes_out_with_the_headers_of_a_page_that_runs_and_no_others(client, store: Store):
    art = _canvas(store, "html", "<p>hi</p>")
    reply = client.get(f"/api/artifacts/{art}/render", headers={"Accept-Encoding": "identity"})
    assert reply.status_code == 200
    # A second policy with `sandbox` and no `allow-scripts` would tell the page to run and not to,
    # and a `Content-Disposition` would save it instead of showing it.
    assert reply.headers.get_list("content-security-policy") == [POLICY, FRAME_ANCESTORS]
    assert reply.headers["content-type"] == "text/html; charset=utf-8"
    assert reply.headers["x-content-type-options"] == "nosniff"
    assert reply.headers["referrer-policy"] == "no-referrer"
    assert reply.headers["x-dns-prefetch-control"] == "off"
    assert reply.headers["cache-control"] == "no-store"
    assert set(reply.headers) - {"vary"} == HEADER_NAMES


def test_an_html_canvas_is_its_own_page_with_the_reporter_added(client, store: Store):
    page = "<!doctype html><title>Trang</title><h1>Chào</h1>"
    art = _canvas(store, "html", page)
    reply = client.get(f"/api/artifacts/{art}/render")
    assert reply.status_code == 200
    assert reply.text == html_page(page)


def test_a_mermaid_canvas_is_a_page_that_draws_its_source(client, store: Store):
    source = "graph TD\n  A --> B\n"
    art = _canvas(store, "mermaid", source, title="Sơ đồ")
    reply = client.get(f"/api/artifacts/{art}/render")
    assert reply.status_code == 200
    assert reply.text == mermaid_page("Sơ đồ", source)


def test_the_newest_version_is_the_page_unless_one_is_asked_for(client, store: Store):
    art = _canvas(store, "html", "<p>một</p>")
    store.artifacts.write(art, "<p>hai</p>", "agent:coach", "")
    url = f"/api/artifacts/{art}/render"
    assert client.get(url).text == html_page("<p>hai</p>")
    assert client.get(url, params={"version": 2}).text == html_page("<p>hai</p>")
    assert client.get(url, params={"version": 1}).text == html_page("<p>một</p>")


@pytest.mark.parametrize("version", ["0", "-1", "abc"])
def test_a_version_is_a_positive_number(client, store: Store, version):
    art = _canvas(store, "html", "<p>x</p>")
    reply = client.get(f"/api/artifacts/{art}/render", params={"version": version})
    assert reply.status_code == 422


@pytest.mark.parametrize("kind", ["markdown", "code", "svg", "image"])
def test_a_canvas_that_is_not_a_page_has_none(client, store: Store, kind):
    if kind == "image":
        art = store.artifacts.create("Ảnh", kind, "", USER, "", None, PICTURE).id
    else:
        art = _canvas(store, kind, "<svg></svg>")
    for params in ({}, {"version": 1}):
        reply = client.get(f"/api/artifacts/{art}/render", params=params)
        assert (reply.status_code, reply.json()["detail"]) == (404, NOT_A_PAGE), params


def test_a_canvas_that_is_not_there_has_no_page(client):
    reply = client.get("/api/artifacts/nope/render")
    assert (reply.status_code, reply.json()["detail"]) == (404, "artifact not found")


def test_a_version_that_is_gone_is_404_with_the_newest_number(client, store: Store, canvas_clock):
    art = _canvas(store, "html", "<p>một</p>")
    store.artifacts.write(art, "<p>hai</p>", USER, "")
    store.artifacts.write(art, "<p>ba</p>", USER, "")  # folds version 2 into 3
    for version in (2, 9):
        reply = client.get(f"/api/artifacts/{art}/render", params={"version": version})
        assert (reply.status_code, reply.json()["detail"]) == (404, {"head_version": 3}), version


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_the_render_address_only_answers_to_get(client, store: Store, method):
    # The local guard lets this one API address through for a request from another site, which
    # is safe only while nothing at it can change anything.
    art = _canvas(store, "html", "<p>x</p>")
    reply = getattr(client, method)(f"/api/artifacts/{art}/render")
    assert reply.status_code == 405
    assert store.artifacts.head(art).version == 1
