"""Only this server's own page, or a program on the machine, may use the API: a page on
another site that reached the port by DNS rebinding is refused on every route, and a browser
request that says it came from another site or another port is refused on the API."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import load_settings
from my_agent_crew.server.app import create_app
from my_agent_crew.server.local_guard import allowed_hosts, cross_site_refusal, is_local_request
from my_agent_crew.server.runtime_build import build_runtime
from my_agent_crew.texts_credentials import CROSS_SITE_REQUEST

NONE: frozenset[str] = frozenset()


@pytest.mark.parametrize(
    ("host", "origin", "extra", "allowed"),
    [
        ("localhost:8765", None, NONE, True),
        ("127.0.0.1:8765", None, NONE, True),
        ("[::1]:8765", None, NONE, True),
        ("100.64.0.9:8765", None, NONE, True),  # reached by its address, e.g. over a VPN
        ("evil.example:8765", None, NONE, False),
        ("mac.tail-net.ts.net", None, frozenset({"mac.tail-net.ts.net"}), True),
        ("127.0.0.1:8765", "http://127.0.0.1:8765", NONE, True),
        ("localhost:5173", "http://localhost:5173", NONE, True),  # the Vite dev proxy
        ("127.0.0.1:8765", "http://localhost:5173", NONE, False),  # another local page
        ("127.0.0.1:8765", "http://127.0.0.1:9999", NONE, False),
        ("100.64.0.9:8765", "http://100.64.0.9:8765", NONE, True),
        ("127.0.0.1:8765", "http://evil.example", NONE, False),
        ("127.0.0.1:8765", "null", NONE, False),
        ("127.0.0.1:8765", "http://[", NONE, False),
        ("[", None, NONE, False),
        ("", None, NONE, False),
    ],
)
def test_who_may_use_the_api(host, origin, extra, allowed) -> None:
    assert is_local_request(host, origin, extra) is allowed


def test_extra_names_are_read_from_a_comma_list() -> None:
    env = {"MY_AGENT_ALLOWED_HOSTS": " Mac.Tail.ts.net , ,other "}
    assert allowed_hosts(env) == {"mac.tail.ts.net", "other"}
    assert allowed_hosts({}) == frozenset()


def test_every_path_is_guarded_the_page_included(tmp_path: Path) -> None:
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"})
    app = create_app(build_runtime(settings), schedule=False)
    rebound = TestClient(app, base_url="http://evil.example:8765")
    local = TestClient(app, base_url="http://127.0.0.1:8765")
    with rebound, local:
        assert rebound.get("/api/agents").status_code == 403
        assert rebound.patch("/api/agents/default", json={}).status_code == 403
        assert local.get("/api/agents").status_code == 200
        foreign = local.get("/api/agents", headers={"Origin": "http://evil.example"})
        assert foreign.status_code == 403
        assert rebound.get("/").status_code == 403
        assert local.get("/").status_code == 200


def test_the_page_route_never_serves_a_file_outside_the_bundle(tmp_path: Path) -> None:
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"})
    local = TestClient(create_app(build_runtime(settings), schedule=False))
    local.base_url = "http://127.0.0.1:8765"
    with local:
        for depth in range(1, 6):
            reply = local.get("/" + "..%2F" * depth + "pyproject.toml")
            assert "[project]" not in reply.text


def test_a_refused_name_is_told_how_to_allow_it_and_logged_once(tmp_path: Path, caplog) -> None:
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"})
    app = create_app(build_runtime(settings), schedule=False)
    by_name = TestClient(app, base_url="http://mac.tail-net.ts.net:8765")
    with by_name, caplog.at_level("WARNING", logger="my_agent_crew.server.local_guard"):
        first = by_name.get("/api/agents")
        by_name.get("/api/agents")
        TestClient(app, base_url="http://mac.tail-net.ts.net:9999").get("/api/agents")
        foreign = TestClient(app, base_url="http://127.0.0.1:8765").get(
            "/api/agents", headers={"Origin": "http://evil.example"}
        )

    detail = first.json()["detail"]
    assert "mac.tail-net.ts.net" in detail and "MY_AGENT_ALLOWED_HOSTS" in detail
    # A wrong Origin is not a name to allow, so it gets no such advice.
    assert "MY_AGENT_ALLOWED_HOSTS" not in foreign.json()["detail"]
    # Once per name, whatever the port; a wrong Origin is not logged as a name to allow.
    refusals = [r for r in caplog.records if "refused a request" in r.getMessage()]
    assert [r.getMessage().count("mac.tail-net.ts.net") for r in refusals] == [1]


@pytest.mark.parametrize(
    ("path", "fetch_site", "refused"),
    [
        ("/api/conversations", None, False),  # curl, the eval runner, Telegram: no such header
        ("/api/conversations", "same-origin", False),  # the page's own calls, the Vite proxy too
        ("/api/conversations", "none", False),  # an address typed or a bookmark opened
        ("/api/conversations", "cross-site", True),  # another site, or a sandboxed page's origin
        ("/api/conversations", "same-site", True),  # another port of this machine
        ("/api/conversations", "made-up", True),  # a value this code does not know is not trusted
        ("/", "cross-site", False),  # a link from elsewhere into the app has to open it
        ("/conversations/abc", "same-site", False),
        ("/assets/index.js", "cross-site", False),
        ("/apiary", "cross-site", False),  # only the API itself, not a path that starts alike
        # A canvas's render page runs in an opaque origin, and a reload of it is cross-site.
        ("/api/artifacts/abc/render", "cross-site", False),
        ("/api/artifacts/abc/render", "same-site", False),
        ("/api/artifacts/abc/render", "made-up", False),
        # Only that address, whole: nothing beside it, under it or built from it.
        ("/api/artifacts/abc/render/", "cross-site", True),
        ("/api/artifacts/abc/render\n", "cross-site", True),  # what `%0A` decodes to
        ("/api/artifacts/abc/render/x", "cross-site", True),
        ("/api/artifacts/a/b/render", "cross-site", True),  # what `a%2Fb` decodes to
        ("/api/artifacts//render", "cross-site", True),
        ("/api/artifacts/render", "cross-site", True),
        ("/api/artifacts/abc", "cross-site", True),
        ("/api/artifacts/abc/raw", "same-site", True),
        ("/api/artifacts/abc/versions", "cross-site", True),
        ("/api/conversations/render", "cross-site", True),
    ],
)
def test_a_browser_request_to_the_api_must_not_say_it_came_from_elsewhere(
    path, fetch_site, refused
) -> None:
    assert cross_site_refusal(path, fetch_site) == (CROSS_SITE_REQUEST if refused else None)


def test_cross_site_requests_are_refused_on_every_method_and_the_page_still_opens(
    tmp_path: Path, caplog
) -> None:
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"})
    app = create_app(build_runtime(settings), schedule=False)
    local = TestClient(app, base_url="http://127.0.0.1:8765")
    with local, caplog.at_level("WARNING", logger="my_agent_crew.server.local_guard"):
        for site in ("cross-site", "same-site"):
            headers = {"Sec-Fetch-Site": site}
            for reply in (
                local.get("/api/conversations", headers=headers),
                local.post("/api/conversations", json={}, headers=headers),
                local.delete("/api/conversations/none", headers=headers),
                # The path the router matches, not the raw one: `%61` is an `a`, `%2F` a slash.
                local.get("/%61pi/conversations", headers=headers),
                local.get("/api%2Fconversations", headers=headers),
            ):
                assert reply.status_code == 403, (site, reply.request.url)
                assert reply.json() == {"detail": CROSS_SITE_REQUEST}
        for site in ("same-origin", "none"):
            own = local.get("/api/conversations", headers={"Sec-Fetch-Site": site})
            assert own.status_code == 200, site
        assert local.get("/api/conversations").status_code == 200
        page = local.get("/", headers={"Sec-Fetch-Site": "cross-site"})
        assert page.status_code == 200 and 'id="root"' in page.text
    # The refusal is not about a name, so it is not logged as one to allow.
    assert not [r for r in caplog.records if "refused a request" in r.getMessage()]


def test_only_the_render_page_of_a_canvas_is_open_to_a_request_from_elsewhere(
    tmp_path: Path,
) -> None:
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"})
    app = create_app(build_runtime(settings), schedule=False)
    local = TestClient(app, base_url="http://127.0.0.1:8765")
    with local:
        made = local.post(
            "/api/artifacts", json={"title": "Trang", "kind": "html", "content": "<p>hi</p>"}
        )
        art = made.json()["id"]
        page = f"/api/artifacts/{art}/render"
        for site in ("cross-site", "same-site"):
            headers = {"Sec-Fetch-Site": site}
            shown = local.get(page, headers=headers)
            assert shown.status_code == 200, site
            assert "<p>hi</p>" in shown.text
            for path in (
                f"/api/artifacts/{art}",
                f"/api/artifacts/{art}/raw",
                f"/api/artifacts/{art}/versions",
                "/api/artifacts",
                f"{page}/",
                f"{page}/x",
                f"{page}%0A",
                "/api/artifacts/a%2Fb/render",
            ):
                refused = local.get(path, headers=headers)
                assert refused.status_code == 403, (site, path)
                assert refused.json() == {"detail": CROSS_SITE_REQUEST}
        # The exception is for the address only: a foreign name or Origin is still turned away.
        assert local.get(page, headers={"Origin": "null"}).status_code == 403
        assert TestClient(app, base_url="http://evil.example:8765").get(page).status_code == 403


def test_a_foreign_name_is_still_told_its_way_in_when_the_request_is_also_cross_site(
    tmp_path: Path,
) -> None:
    settings = load_settings(env={"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"})
    app = create_app(build_runtime(settings), schedule=False)
    by_name = TestClient(app, base_url="http://mac.tail-net.ts.net:8765")
    with by_name:
        reply = by_name.get("/api/agents", headers={"Sec-Fetch-Site": "cross-site"})
    assert reply.status_code == 403
    assert "MY_AGENT_ALLOWED_HOSTS" in reply.json()["detail"]
