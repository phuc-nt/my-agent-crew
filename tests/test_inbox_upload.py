"""A file added to a message in the web box lands in the agent's inbox the way a Telegram
attachment does, and the answer names it with the line the thread shows as a thumbnail."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import load_settings
from my_agent_crew.inbox_files import free_path, inbox_file
from my_agent_crew.server import build_runtime, create_app, routes_inbox_upload
from my_agent_crew.texts import TELEGRAM_ATTACHMENT_LINE


@pytest.fixture
def served(tmp_path: Path):
    coach = tmp_path / "agents" / "coach"
    coach.mkdir(parents=True)
    (coach / "agent.yaml").write_text("name: Coach\nroutes: [fake:echo]\n")
    env = {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, runtime


def test_a_picture_is_saved_in_the_agents_inbox_and_named_by_the_attachment_line(served):
    client, runtime = served
    r = client.post("/api/agents/coach/inbox", params={"name": "receipt.png"}, content=b"\x89PNG x")
    assert r.status_code == 201
    path = Path(r.json()["path"])
    inbox = runtime.deps_for("coach").agent.workspace / "inbox"
    assert path.parent == inbox and path.name.endswith("-receipt.png")
    assert path.read_bytes() == b"\x89PNG x"
    assert r.json()["line"] == TELEGRAM_ATTACHMENT_LINE.format(path=path)
    # The thread serves it back through the agent's own files route.
    shown = client.get("/api/agents/coach/files", params={"path": str(path)})
    assert shown.status_code == 200 and shown.content == b"\x89PNG x"


def test_two_files_of_one_name_in_the_same_second_both_stay(served):
    client, _ = served
    paths = {
        client.post("/api/agents/coach/inbox", params={"name": "a.jpg"}, content=body).json()[
            "path"
        ]
        for body in (b"one", b"two")
    }
    assert len(paths) == 2
    assert sorted(Path(p).read_bytes() for p in paths) == [b"one", b"two"]


def test_a_crafted_name_cannot_leave_the_inbox(served):
    client, runtime = served
    r = client.post("/api/agents/coach/inbox", params={"name": "../../agent.yaml"}, content=b"x")
    path = Path(r.json()["path"])
    assert path.parent == runtime.deps_for("coach").agent.workspace / "inbox"
    assert path.name.endswith("-agent.yaml")


def test_an_empty_or_oversized_file_and_an_unknown_agent_are_refused(served, monkeypatch):
    client, _ = served
    assert (
        client.post("/api/agents/coach/inbox", params={"name": "a.png"}, content=b"").status_code
        == 422
    )
    assert (
        client.post("/api/agents/nope/inbox", params={"name": "a.png"}, content=b"x").status_code
        == 404
    )
    monkeypatch.setattr(routes_inbox_upload, "MAX_UPLOAD_BYTES", 4)
    r = client.post("/api/agents/coach/inbox", params={"name": "a.png"}, content=b"12345")
    assert r.status_code == 413


def test_inbox_names_are_stamped_and_never_overwrite(tmp_path: Path):
    now = datetime(2026, 11, 9, 13, 5, 7)
    assert inbox_file(tmp_path, "", "photo", now).name == "20261109-130507-photo"
    first = inbox_file(tmp_path, "a b.png", "file", now)
    assert first.name == "20261109-130507-a_b.png"
    first.write_bytes(b"x")
    assert free_path(first).name == "20261109-130507-a_b-2.png"
