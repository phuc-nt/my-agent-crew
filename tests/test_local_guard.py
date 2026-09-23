"""Only this server's own page, or a program on the machine, may use the API: a page on
another site that reached the port by DNS rebinding is refused on every route."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import load_settings
from my_agent_crew.server.app import create_app
from my_agent_crew.server.local_guard import allowed_hosts, is_local_request
from my_agent_crew.server.runtime_build import build_runtime

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
