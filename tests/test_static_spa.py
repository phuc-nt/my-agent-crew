"""The committed web bundle is served by the same process as the API."""

import json
import re

from fastapi.testclient import TestClient

from my_agent_crew.server import create_app
from my_agent_crew.server.app import STATIC_DIR


def test_bundle_is_present_so_the_server_works_out_of_the_box():
    assert (STATIC_DIR / "index.html").is_file()
    assert any((STATIC_DIR / "assets").glob("*.js"))


def test_root_and_unknown_paths_serve_the_spa_while_api_404s_stay_json(deps_factory):
    client = TestClient(create_app(deps_factory()), base_url="http://127.0.0.1")
    root = client.get("/")
    assert root.status_code == 200
    assert 'id="root"' in root.text
    deep = client.get("/conversations/abc")
    assert deep.status_code == 200 and deep.text == root.text
    missing = client.get("/api/definitely-not-a-route")
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/json")


def test_bundled_assets_are_served_with_their_real_content(deps_factory):
    client = TestClient(create_app(deps_factory()), base_url="http://127.0.0.1")
    script = next((STATIC_DIR / "assets").glob("*.js"))
    response = client.get(f"/assets/{script.name}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert response.content == script.read_bytes()


def test_every_icon_the_page_and_its_manifest_name_is_in_the_bundle(deps_factory):
    """A missing icon fails quietly: the tab shows a blank square and nothing logs it."""
    client = TestClient(create_app(deps_factory()), base_url="http://127.0.0.1")
    page = (STATIC_DIR / "index.html").read_text()
    linked = re.findall(r'<link rel="(?:icon|apple-touch-icon|manifest)" href="/([^"]+)"', page)
    assert {"favicon.svg", "apple-touch-icon.png", "manifest.webmanifest"} <= set(linked)
    manifest = client.get("/manifest.webmanifest")
    assert manifest.headers["content-type"].startswith("application/manifest+json")
    declared = json.loads(manifest.text)["icons"]
    assert any(icon.get("purpose") == "maskable" for icon in declared)
    types = {
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".webmanifest": "application/manifest+json",
    }
    for name in {*linked, *(icon["src"].lstrip("/") for icon in declared)}:
        response = client.get(f"/{name}")
        assert response.status_code == 200, name
        assert response.content == (STATIC_DIR / name).read_bytes(), name
        suffix = name[name.rindex(".") :]
        assert response.headers["content-type"].startswith(types[suffix]), name
