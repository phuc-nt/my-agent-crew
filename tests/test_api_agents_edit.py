from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.config import load_settings
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime_build import build_runtime


@pytest.fixture
def crew(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False)) as client:
        yield client, runtime, home


def test_creating_an_agent_puts_it_on_disk_and_in_the_crew(crew) -> None:
    client, runtime, home = crew

    reply = client.post(
        "/api/agents",
        json={"agent_id": "coder", "profile": {"name": "Thợ mã", "description": "dọn mã"}},
    )

    assert reply.status_code == 201
    assert reply.json()["profile"]["name"] == "Thợ mã"
    assert (home / "agents" / "coder" / "agent.yaml").is_file()
    # On disk is not enough: the master has to be able to hand it work right away.
    assert runtime.deps_for("coder").agent.name == "Thợ mã"
    assert "coder" in client.get("/api/agents/default").json()["delegates"]


def test_an_id_that_is_not_a_safe_folder_name_is_refused(crew) -> None:
    client, _, home = crew

    reply = client.post("/api/agents", json={"agent_id": "../escape", "profile": {}})

    assert reply.status_code == 422
    assert not (home / "agents").exists()


def test_creating_an_agent_that_already_exists_says_so(crew) -> None:
    client, _, _ = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})

    reply = client.post("/api/agents", json={"agent_id": "coder", "profile": {}})

    assert reply.status_code == 409
    assert "coder" in reply.json()["detail"]


def test_a_patch_changes_only_the_keys_it_names(crew) -> None:
    client, runtime, home = crew
    client.post(
        "/api/agents",
        json={"agent_id": "coder", "profile": {"name": "Thợ mã", "description": "dọn mã"}},
    )

    reply = client.patch("/api/agents/coder", json={"profile": {"cost_cap_usd": 7.5}})

    assert reply.status_code == 200
    assert reply.json()["profile"]["cost_cap_usd"] == 7.5
    assert runtime.deps_for("coder").agent.settings.cost_cap_usd == 7.5
    written = (home / "agents" / "coder" / "agent.yaml").read_text(encoding="utf-8")
    assert "dọn mã" in written


def test_clearing_a_key_takes_an_explicit_null(crew) -> None:
    client, runtime, _ = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {"description": "dọn mã"}})

    client.patch("/api/agents/coder", json={"profile": {"description": None}})

    assert runtime.deps_for("coder").agent.description == ""


def test_a_profile_the_server_would_not_start_with_is_refused_before_it_is_written(
    crew,
) -> None:
    client, runtime, home = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {"name": "Thợ mã"}})

    reply = client.patch("/api/agents/coder", json={"profile": {"mode": "bừa"}})

    assert reply.status_code == 422
    # Neither the file nor the running agent may carry a value that fails to parse.
    assert "bừa" not in (home / "agents" / "coder" / "agent.yaml").read_text(encoding="utf-8")
    assert runtime.deps_for("coder").agent.mode == "assistant"


def test_a_key_the_profile_has_no_place_for_is_named_back(crew) -> None:
    client, _, _ = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})

    reply = client.patch("/api/agents/coder", json={"profile": {"colour": "xanh"}})

    assert reply.status_code == 422
    assert "colour" in reply.json()["detail"]


def test_delegating_to_an_agent_that_does_not_exist_is_refused(crew) -> None:
    client, _, _ = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})

    reply = client.patch("/api/agents/coder", json={"profile": {"delegates": ["ma"]}})

    assert reply.status_code == 422


def test_a_plain_new_agent_does_not_ask_for_a_restart(crew) -> None:
    client, _, _ = crew

    reply = client.post("/api/agents", json={"agent_id": "coder", "profile": {"name": "Thợ"}})

    # It is live the moment it is created; a notice shown every time would be ignored by
    # the time it is true.
    assert reply.json()["restart_required"] == []


def test_only_a_schedule_or_a_channel_asks_for_a_restart(crew) -> None:
    client, _, _ = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})

    renamed = client.patch("/api/agents/coder", json={"profile": {"name": "Thợ mã"}})
    scheduled = client.patch(
        "/api/agents/coder",
        json={
            "profile": {
                "schedules": [{"id": "sáng", "cron": "0 7 * * *", "prompt": "chào"}]
            }
        },
    )

    dropped = client.patch("/api/agents/coder", json={"profile": {"schedules": None}})

    assert renamed.json()["restart_required"] == []
    assert scheduled.json()["restart_required"] == ["Lịch chạy mới cần khởi động lại máy chủ."]
    # The clock keeps the job it started with, so taking one away needs the restart too.
    assert dropped.json()["restart_required"] == ["Lịch chạy mới cần khởi động lại máy chủ."]


def test_the_master_is_editable_and_its_file_lands_in_the_home(crew) -> None:
    client, runtime, home = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})

    reply = client.patch("/api/agents/default", json={"profile": {"name": "Thư ký"}})

    # The master has no manifest until the first edit writes one, so it is editable on
    # the strength of being the master; an agent the API created has the file itself.
    assert client.get("/api/agents/default").json()["editable"] is True
    assert client.get("/api/agents/coder").json()["editable"] is True
    assert reply.status_code == 200
    assert (home / "agent.yaml").is_file()
    assert runtime.default.agent.name == "Thư ký"


def test_the_master_cannot_be_removed(crew) -> None:
    client, runtime, _ = crew

    reply = client.delete("/api/agents/default")

    assert reply.status_code == 409
    assert runtime.deps_for("default") is not None


def test_removing_an_agent_keeps_its_folder_and_takes_it_out_of_the_crew(crew) -> None:
    client, runtime, home = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {"name": "Thợ mã"}})

    reply = client.delete("/api/agents/coder")

    assert reply.status_code == 200
    assert Path(reply.json()["kept_at"]).is_dir()
    assert not (home / "agents" / "coder").exists()
    assert "coder" not in runtime.agents
    assert "coder" not in client.get("/api/agents/default").json()["delegates"]


def test_an_agent_someone_still_delegates_to_is_not_removed(crew) -> None:
    client, _, _ = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
    client.post("/api/agents", json={"agent_id": "lead", "profile": {"delegates": ["coder"]}})

    reply = client.delete("/api/agents/coder")

    assert reply.status_code == 409
    assert "lead" in reply.json()["detail"]


def test_a_persona_file_is_written_by_name_and_nothing_else_is(crew) -> None:
    client, _, home = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})

    written = client.put(
        "/api/agents/coder/files/AGENTS.md", json={"content": "Luôn viết test trước."}
    )
    unlisted = client.put("/api/agents/coder/files/NOTES.md", json={"content": "x"})
    escaped = client.put("/api/agents/coder/files/..%2F..%2Fagent.yaml", json={"content": "x"})

    assert written.status_code == 200
    body = (home / "agents" / "coder" / "AGENTS.md").read_text(encoding="utf-8")
    assert body == "Luôn viết test trước."
    # The name is matched against the persona list, so nothing else is created, and a
    # path dressed up as a name never reaches the handler at all.
    assert unlisted.status_code == 404
    assert not (home / "agents" / "coder" / "NOTES.md").exists()
    assert escaped.status_code in (404, 405)
    assert not (home / "agents" / "agent.yaml").exists()


def test_a_persona_file_reads_back_and_an_unwritten_one_reads_empty(crew) -> None:
    client, _, _ = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
    client.put("/api/agents/coder/files/AGENTS.md", json={"content": "Luôn viết test trước."})

    written = client.get("/api/agents/coder/files/AGENTS.md")
    untouched = client.get("/api/agents/coder/files/SOUL.md")
    unlisted = client.get("/api/agents/coder/files/NOTES.md")

    assert written.json() == {
        "name": "AGENTS.md",
        "content": "Luôn viết test trước.",
        "chars": len("Luôn viết test trước."),
    }
    # Every agent starts with none of these written; an editor that could not open one
    # would leave no way to write its first line.
    assert untouched.status_code == 200
    assert untouched.json()["content"] == ""
    assert unlisted.status_code == 404


REVIEWER_MD = """---
name: Reviewer
description: Đọc mã và báo lại.
---
Bạn đọc mã.
"""


def test_an_agent_that_came_from_a_kit_is_read_only_and_says_where_it_lives(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    (home / ".agents" / "agents").mkdir(parents=True)
    (home / ".agents" / "agents" / "reviewer.md").write_text(REVIEWER_MD, encoding="utf-8")
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False)) as client:
        patched = client.patch("/api/agents/reviewer", json={"profile": {"name": "Khác"}})
        deleted = client.delete("/api/agents/reviewer")
        described = client.get("/api/agents/reviewer").json()

    # The listing says so too, so an editor can refuse the form rather than let someone
    # fill one in and find out at the save.
    assert described["editable"] is False
    assert patched.status_code == 409
    # The refusal names the markdown file, because that is the only place an edit works.
    assert "reviewer.md" in patched.json()["detail"]
    assert deleted.status_code == 409
    assert (home / ".agents" / "agents" / "reviewer.md").is_file()


def test_editing_an_agent_that_is_not_there_is_a_404(crew) -> None:
    client, _, _ = crew

    assert client.patch("/api/agents/ma", json={"profile": {}}).status_code == 404
    assert client.delete("/api/agents/ma").status_code == 404


def test_a_persona_file_outside_the_home_is_refused(crew, tmp_path: Path) -> None:
    client, runtime, _ = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
    secret = tmp_path / "credentials.txt"
    secret.write_text("OPENROUTER_API_KEY=sk-that-must-not-travel", encoding="utf-8")

    reply = client.patch("/api/agents/coder", json={"profile": {"persona_files": [str(secret)]}})

    # A persona file is read into the system prompt and goes to the model on the next
    # turn, so naming one outside the home would hand any readable file to the provider.
    assert reply.status_code == 422
    assert str(secret) not in str(runtime.deps_for("coder").agent.persona_files)


def test_a_workspace_outside_the_home_is_refused(crew) -> None:
    client, runtime, _ = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
    before = runtime.deps_for("coder").agent.workspace

    absolute = client.patch("/api/agents/coder", json={"profile": {"workspace": "~/escape"}})
    # Far enough up to leave the home: an agent lives at <home>/agents/<id>, so two
    # levels still lands inside it and only the third one gets out.
    upward = client.patch(
        "/api/agents/coder", json={"profile": {"workspace": "../../../escape"}}
    )
    sideways = client.patch("/api/agents/coder", json={"profile": {"workspace": "../shared"}})

    # The workspace is what every file tool is scoped to; pointing it at the source tree
    # would let an agent rewrite the code that runs it.
    assert absolute.status_code == 422
    assert upward.status_code == 422
    # Still inside the home, so it is a layout choice rather than an escape.
    assert sideways.status_code == 200
    assert runtime.deps_for("coder").agent.workspace != before


def test_a_skills_dir_outside_the_home_is_refused(crew) -> None:
    client, _, _ = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})

    reply = client.patch("/api/agents/coder", json={"profile": {"skills_dirs": ["~/elsewhere"]}})

    assert reply.status_code == 422


def test_the_ask_list_cannot_be_turned_into_single_letters(crew) -> None:
    client, runtime, _ = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
    before = runtime.deps_for("coder").agent.settings.shell_ask_patterns

    reply = client.patch("/api/agents/coder", json={"profile": {"shell_ask_patterns": "rm"}})

    # A string is iterable: taken as a list it becomes the patterns "r" and "m", which
    # match nearly every command and so stop meaning anything.
    assert reply.status_code == 422
    assert runtime.deps_for("coder").agent.settings.shell_ask_patterns == before


def test_an_edit_the_crew_refuses_does_not_reach_the_file(crew) -> None:
    client, runtime, home = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {"name": "Thợ mã"}})
    runtime.client = None

    reply = client.patch("/api/agents/coder", json={"profile": {"name": "Không được ghi"}})

    # The answer said no, so the file has to say no too — otherwise the edit would
    # arrive on its own at the next restart.
    assert reply.status_code == 409
    written = (home / "agents" / "coder" / "agent.yaml").read_text(encoding="utf-8")
    assert "Không được ghi" not in written
    assert runtime.deps_for("coder").agent.name == "Thợ mã"
