"""A picture canvas over REST: the panel's save carries text, and a picture holds none, so
the save is refused and the picture stays as it was."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.server import create_app
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(32))


@pytest.fixture
def client(deps_factory):
    app = create_app(deps_factory(), schedule=False)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client


def test_saving_text_onto_a_picture_canvas_is_422_and_the_picture_stays(client, store: Store):
    art = store.artifacts.create("Ảnh bìa", "image", "", USER, "", data=PNG).id
    saved = client.put(f"/api/artifacts/{art}", json={"content": "chữ", "base_version": 1})
    assert (saved.status_code, saved.json()["detail"]) == (422, "image takes data, not content")
    assert [version.version for version in store.artifacts.versions(art)] == [1]
    head = store.artifacts.head(art)
    assert (head.data, head.content) == (PNG, None)
