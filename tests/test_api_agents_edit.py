import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew import texts
from my_agent_crew.config import load_settings
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime_build import build_runtime


@pytest.fixture
def crew(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
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


@pytest.mark.parametrize("agent_id", ["../escape", "coder\n"])
def test_an_id_that_is_not_a_safe_folder_name_is_refused(crew, agent_id) -> None:
    client, _, home = crew

    reply = client.post("/api/agents", json={"agent_id": agent_id, "profile": {}})

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


def test_routes_sent_as_a_provider_and_a_model_are_saved_the_way_a_person_writes_them(
    crew,
) -> None:
    """The agent editor holds a route as a provider and a model apart and sends it so."""
    client, runtime, home = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})

    reply = client.patch(
        "/api/agents/coder",
        json={"profile": {"routes": [{"provider": " fake ", "model": "two"}, "fake:three"]}},
    )

    assert reply.status_code == 200
    wanted = [{"provider": "fake", "model": "two"}, {"provider": "fake", "model": "three"}]
    assert reply.json()["profile"]["routes"] == wanted
    asked = [(r.provider, r.model) for r in runtime.deps_for("coder").chain.routes]
    assert asked == [("fake", "two"), ("fake", "three")]
    written = (home / "agents" / "coder" / "agent.yaml").read_text(encoding="utf-8")
    assert "- fake:two\n" in written and "provider" not in written


@pytest.mark.parametrize(
    "route",
    [
        {"provider": "fake"},
        {"provider": "", "model": "two"},
        {"provider": "fake", "model": 3},
        {"provider": "fake", "model": "two", "reasoning": "high"},
        7,
    ],
)
def test_a_route_that_is_not_a_provider_and_a_model_is_refused_before_it_is_written(
    crew, route
) -> None:
    client, runtime, home = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})

    reply = client.patch("/api/agents/coder", json={"profile": {"routes": [route]}})

    assert reply.status_code == 422 and "provider:model" in reply.json()["detail"]
    assert "routes" not in (home / "agents" / "coder" / "agent.yaml").read_text(encoding="utf-8")
    assert [r.model for r in runtime.deps_for("coder").chain.routes] == ["echo"]


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


def test_only_a_schedule_asks_for_a_restart(crew) -> None:
    client, _, _ = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})

    renamed = client.patch("/api/agents/coder", json={"profile": {"name": "Thợ mã"}})
    scheduled = client.patch(
        "/api/agents/coder",
        json={"profile": {"schedules": [{"id": "sáng", "cron": "0 7 * * *", "prompt": "chào"}]}},
    )

    dropped = client.patch("/api/agents/coder", json={"profile": {"schedules": None}})
    consolidating = client.patch(
        "/api/agents/coder", json={"profile": {"memory_consolidate": "0 3 * * *"}}
    )

    assert renamed.json()["restart_required"] == []
    assert scheduled.json()["restart_required"] == [texts.RESTART_REASON_SCHEDULES]
    # The clock keeps the job it started with, so taking one away needs the restart too.
    assert dropped.json()["restart_required"] == [texts.RESTART_REASON_SCHEDULES]
    # Consolidation is one more job on that clock. The editor shows each reason as the
    # sentence it is, so it gets the same one, once, and not the name of the key.
    assert consolidating.json()["restart_required"] == [texts.RESTART_REASON_SCHEDULES]


def test_the_web_fakes_answer_a_schedule_edit_with_the_servers_own_reason():
    """The web's fakes answer a save with this sentence (`SCHEDULES_RESTART_REASON` in
    web/src/test/schedule-contract.ts). Reworded on one side only, the editor's tests would
    go on checking a banner the server no longer shows."""
    contract = Path(__file__).resolve().parents[1] / "web" / "src" / "test" / "schedule-contract.ts"
    mirrored = re.search(
        r'^export const SCHEDULES_RESTART_REASON = "([^"]+)";$', contract.read_text("utf-8"), re.M
    )
    assert mirrored is not None
    assert mirrored.group(1) == texts.RESTART_REASON_SCHEDULES


def test_a_saved_schedule_comes_back_in_the_shape_it_can_be_resent_in(crew) -> None:
    client, _, _ = crew
    created = client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
    row = {"id": "dọn", "name": "Dọn rác", "every": "30m", "command": "echo hi", "skills": []}

    saved = client.patch("/api/agents/coder", json={"profile": {"schedules": [row]}})

    assert saved.status_code == 200
    profile = saved.json()["profile"]
    # The editor rebuilds its form from this answer, so it carries what the list does:
    # without `declared` the page that made the save had nothing left to diff against.
    assert created.json()["profile"]["declared"] == {"delegates": [], "schedules": []}
    # Names, as the list gives them, not the detail page's descriptions.
    assert profile["tools"] and all(isinstance(n, str) for n in profile["tools"])
    assert all(isinstance(n, str) for n in profile["skills"])
    declared = profile["declared"]["schedules"]
    unset = {"cron": None, "prompt": None, "enabled": True, "approval_ttl_seconds": None}
    assert declared == [{**row, **unset}]
    again = client.patch("/api/agents/coder", json={"profile": {"schedules": declared}})
    assert again.status_code == 200
    assert again.json()["profile"]["declared"]["schedules"] == declared


def test_a_schedule_carrying_its_derived_kind_is_refused(crew) -> None:
    client, _, home = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
    row = {"id": "sáng", "cron": "0 7 * * *", "prompt": "chào", "kind": "prompt"}

    reply = client.patch("/api/agents/coder", json={"profile": {"schedules": [row]}})

    assert reply.status_code == 422
    assert "kind" in reply.json()["detail"]
    assert "schedules" not in (home / "agents" / "coder" / "agent.yaml").read_text("utf-8")


@pytest.mark.parametrize(
    "patch",
    [
        {"schedules": [{"id": "a", "cron": "0 7 * *", "prompt": "chào"}]},
        {"schedules": [{"id": "a", "cron": "0 25 * * *", "prompt": "chào"}]},
        {"schedules": [{"id": "a", "every": "10s", "prompt": "chào"}]},
        {"memory_consolidate": "mỗi đêm"},
    ],
)
def test_a_timing_the_clock_cannot_read_is_refused_before_it_is_written(crew, patch) -> None:
    client, runtime, home = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})

    reply = client.patch("/api/agents/coder", json={"profile": patch})

    # Accepted, it would stop at the next boot's scheduler and take every job with it.
    assert reply.status_code == 422
    assert runtime.deps_for("coder").agent.schedules == ()
    written = (home / "agents" / "coder" / "agent.yaml").read_text("utf-8")
    assert "schedules" not in written and "memory_consolidate" not in written


def test_a_blank_row_that_lands_on_a_kept_rows_id_is_refused(crew) -> None:
    client, runtime, home = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
    blank = {"cron": "0 7 * * *", "prompt": "chào"}
    first = client.patch(
        "/api/agents/coder",
        json={"profile": {"schedules": [{**blank, "name": "A"}, {**blank, "name": "B"}]}},
    )
    kept_b = first.json()["profile"]["declared"]["schedules"][1]

    # A removed and a blank C added: C is numbered by its place, job-1, which B carries.
    reply = client.patch(
        "/api/agents/coder",
        json={"profile": {"schedules": [kept_b, {**blank, "name": "C"}]}},
    )

    # Accepted, the scheduler keys its jobs by id and B would silently never run again.
    assert reply.status_code == 422
    assert "job-1" in reply.json()["detail"]
    assert [s.name for s in runtime.deps_for("coder").agent.schedules] == ["A", "B"]
    assert "name: C" not in (home / "agents" / "coder" / "agent.yaml").read_text("utf-8")


def test_a_schedule_cannot_take_the_consolidation_jobs_id(crew) -> None:
    client, runtime, _ = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
    row = {"id": "memory-consolidate", "cron": "0 7 * * *", "prompt": "chào"}

    reply = client.patch(
        "/api/agents/coder",
        json={"profile": {"schedules": [row], "memory_consolidate": "0 3 * * *"}},
    )

    assert reply.status_code == 422
    assert "memory-consolidate" in reply.json()["detail"]
    assert runtime.deps_for("coder").agent.schedules == ()


# Boots, but the edit path would not have written it: an hour the clock cannot read, and
# two rows on one id.
HAND_WRITTEN_SCHEDULES = """\
name: Thợ mã
schedules:
  - id: sáng
    cron: "0 25 * * *"
    prompt: chào
  - id: tối
    cron: "0 21 * * *"
    prompt: nghỉ
  - id: tối
    cron: "0 22 * * *"
    prompt: ngủ
"""


def test_rows_an_edit_leaves_alone_do_not_hold_the_save(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / "agents" / "coder").mkdir(parents=True)
    manifest = home / "agents" / "coder" / "agent.yaml"
    manifest.write_text(HAND_WRITTEN_SCHEDULES, encoding="utf-8")
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        renamed = client.patch("/api/agents/coder", json={"profile": {"name": "Thợ mới"}})
        consolidating = client.patch(
            "/api/agents/coder", json={"profile": {"memory_consolidate": "0 3 * * *"}}
        )
        kept = client.get("/api/agents/coder").json()["declared"]["schedules"]

        def saving(rows: list[dict]) -> int:
            patch = {"profile": {"schedules": rows}}
            return client.patch("/api/agents/coder", json=patch).status_code

        retimed = saving([kept[0], {**kept[1], "cron": "0 24 * * *"}, kept[2]])
        copied = saving([*kept, kept[1]])
        added = saving([*kept, {"id": "trưa", "cron": "0 12 * * *", "prompt": "ăn"}])

    # The file was taken as it is at boot; an edit to something else in it is no moment to
    # refuse what it already held, and the editor does not re-check keys it did not change.
    assert (renamed.status_code, consolidating.status_code) == (200, 200)
    assert runtime.deps_for("coder").agent.name == "Thợ mới"
    # A row the edit changes is read in full, whatever id it keeps; and a kept row sent a
    # second time is one more job on its id, not a row left alone.
    assert (retimed, copied) == (422, 422)
    assert added == 200
    assert [s.id for s in runtime.deps_for("coder").agent.schedules if not s.consolidate] == [
        "sáng",
        "tối",
        "tối",
        "trưa",
    ]


def test_clearing_memory_consolidation_removes_the_key(crew) -> None:
    client, runtime, home = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
    client.patch("/api/agents/coder", json={"profile": {"memory_consolidate": "0 3 * * *"}})

    reply = client.patch("/api/agents/coder", json={"profile": {"memory_consolidate": None}})

    assert reply.status_code == 200
    assert reply.json()["profile"]["memory_consolidate"] == ""
    assert runtime.deps_for("coder").agent.schedules == ()
    assert "memory_consolidate" not in (home / "agents" / "coder" / "agent.yaml").read_text("utf-8")


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
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
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
    upward = client.patch("/api/agents/coder", json={"profile": {"workspace": "../../../escape"}})
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


def test_the_skills_folders_are_reported_and_survive_an_unrelated_edit(crew) -> None:
    client, runtime, home = crew
    skills_dir = home / "agents" / "coder" / "skills"
    skills_dir.mkdir(parents=True)
    client.post(
        "/api/agents",
        json={"agent_id": "coder", "profile": {"skills_dirs": [str(skills_dir)]}},
    )

    described = client.get("/api/agents/coder").json()
    reply = client.patch("/api/agents/coder", json={"profile": {"name": "Coder mới"}})

    # Reported, so an editor can show where an agent's skills come from rather than
    # leaving a configured folder invisible to the only screen that edits the profile.
    assert str(skills_dir) in described["skills_dirs"]
    # A patch names the keys it changes, so one it leaves out keeps whatever the
    # hand-written file said — which is what lets an editor save a single field safely.
    assert reply.status_code == 200
    assert skills_dir in runtime.deps_for("coder").agent.skills_dirs


def test_giving_the_master_a_bot_starts_it_without_a_restart(crew, monkeypatch) -> None:
    client, runtime, _ = crew
    monkeypatch.setenv("CREW_BOT_TOKEN", "123:test-token")

    reply = client.patch(
        "/api/agents/default",
        json={"profile": {"telegram": {"token_env": "CREW_BOT_TOKEN", "chat_id": 7}}},
    )

    assert reply.status_code == 200
    assert reply.json()["restart_required"] == []
    assert runtime.channel is not None
    # A test app never polls; the rebuilt bot follows the one it replaced.
    assert runtime.channel_live is False

    client.patch("/api/agents/default", json={"profile": {"telegram": None}})

    assert runtime.channel is None
