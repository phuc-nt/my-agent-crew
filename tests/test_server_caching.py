"""What the server does so a page load and a rail refresh cost little: compressed
responses, immutable hashed assets, and stats that are not recomputed between writes."""

from fastapi.testclient import TestClient

from my_agent_crew.server import create_app, routes_activity
from my_agent_crew.server.app import IMMUTABLE_CACHE, STATIC_DIR
from my_agent_crew.server.runtime import Runtime

GZIP = {"accept-encoding": "gzip"}


def test_hashed_assets_are_gzipped_and_cacheable_forever_while_index_is_not(deps_factory):
    client = TestClient(create_app(deps_factory()), base_url="http://127.0.0.1")
    # The largest chunk: the build also emits a runtime stub too small to be worth gzipping.
    script = max((STATIC_DIR / "assets").glob("*.js"), key=lambda p: p.stat().st_size)
    asset = client.get(f"/assets/{script.name}", headers=GZIP)
    assert asset.headers["content-encoding"] == "gzip"
    assert asset.headers["cache-control"] == IMMUTABLE_CACHE
    assert asset.content == script.read_bytes()
    index = client.get("/", headers=GZIP)
    assert "immutable" not in index.headers.get("cache-control", "")


def test_large_api_answers_are_gzipped_and_event_streams_are_not(deps_factory):
    client = TestClient(create_app(deps_factory()), base_url="http://127.0.0.1")
    assert "content-encoding" not in client.get("/api/health", headers=GZIP).headers
    assert client.get("/api/tools", headers=GZIP).headers.get("content-encoding") == "gzip"
    conv = client.post("/api/conversations", json={}).json()
    with client.stream(
        "POST", f"/api/conversations/{conv['id']}/messages", json={"text": "hi"}, headers=GZIP
    ) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        assert "content-encoding" not in r.headers
        r.read()


def test_stats_are_computed_once_between_two_writes(deps_factory):
    runtime = Runtime.single(deps_factory())
    client = TestClient(create_app(runtime), base_url="http://127.0.0.1")
    first = routes_activity.stats(runtime)
    assert routes_activity.stats(runtime) is first
    assert client.get("/api/stats").json() == first
    runtime.store.create()
    assert routes_activity.stats(runtime) is not first
