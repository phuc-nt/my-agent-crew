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
        ("127.0.0.1:8765", "http://localhost:5173", NONE, True),  # the dev server
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


def test_every_api_route_is_guarded_but_the_page_is_not(tmp_path: Path) -> None:
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
        assert rebound.get("/").status_code != 403
