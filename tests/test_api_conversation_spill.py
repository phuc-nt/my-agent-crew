"""Deleting a conversation over HTTP removes the folder its long tool outputs were kept in,
and only that folder; a delete that finds no conversation removes nothing."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import Route
from my_agent_crew.server import create_app
from my_agent_crew.tools.output_spill import Spill


@pytest.fixture
def client(deps_factory):
    deps = deps_factory(routes=(Route("fake", "echo"),))
    with TestClient(create_app(deps), base_url="http://127.0.0.1") as c:
        yield c, deps


def new_conversation(client: TestClient) -> str:
    return client.post("/api/conversations", json={}).json()["id"]


def _spill_files(deps, conv_id: str) -> list[str]:
    folder = deps.settings.home / "spill" / conv_id
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


def test_deleting_a_conversation_removes_its_spill_folder(client):
    c, deps = client
    conv_id = new_conversation(c)
    other = new_conversation(c)
    Spill(deps.settings.home).write(conv_id, "call1", "x" * 10)
    Spill(deps.settings.home).write(other, "call1", "y" * 10)

    assert c.delete(f"/api/conversations/{conv_id}").status_code == 204

    assert _spill_files(deps, conv_id) == []
    assert not (deps.settings.home / "spill" / conv_id).exists()
    assert len(_spill_files(deps, other)) == 1


def test_deleting_an_unknown_conversation_is_404_and_touches_no_spill_folder(client):
    c, deps = client
    conv_id = new_conversation(c)
    Spill(deps.settings.home).write(conv_id, "call1", "x" * 10)

    assert c.delete("/api/conversations/nope").status_code == 404

    assert len(_spill_files(deps, conv_id)) == 1
