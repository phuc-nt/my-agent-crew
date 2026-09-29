"""How long an approval waits for a person, per schedule and per Telegram channel.

A job that opens at three in the morning and asks before it writes got the same ten minutes
as a chat the owner is looking at; nobody is awake to answer, so it expired every night. A
schedule or the Telegram block may now say how long its approvals wait, the conversation it
opens remembers it, and an approval that still runs out is read as a refusal that changed
nothing. These tests pin the declaration and its round trip through the editor; where a
running conversation reads the wait is in test_approval_ttl_runs.py.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.agents.approval_ttl import MAX_TTL, MIN_TTL, effective_ttl
from my_agent_crew.agents.profile_write import read_raw
from my_agent_crew.agents.profile_yaml import parse_profile
from my_agent_crew.agents.schedule import SCHEDULE_KEYS
from my_agent_crew.config import Settings, load_settings
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime_build import build_runtime
from my_agent_crew.store import Store
from my_agent_crew.texts import EXPIRED_TOOL

ROOT = Path(__file__).resolve().parents[1]
MORNING = {"id": "morning", "cron": "0 7 * * *", "prompt": "tóm tắt"}
EVENING = {"id": "evening", "cron": "0 19 * * *", "prompt": "tổng kết"}


def parsed_schedule(raw: dict, settings: Settings, tmp_path: Path):
    profile = parse_profile("a", tmp_path, {"schedules": [raw]}, settings)
    [schedule] = [s for s in profile.schedules if not s.consolidate]
    return schedule


@pytest.mark.parametrize("seconds", [MIN_TTL, 7200, MAX_TTL])
def test_a_schedule_may_say_how_long_its_approvals_wait(settings, tmp_path, seconds):
    schedule = parsed_schedule({**MORNING, "approval_ttl_seconds": seconds}, settings, tmp_path)

    assert schedule.approval_ttl_seconds == seconds
    assert schedule.to_dict()["approval_ttl_seconds"] == seconds


def test_a_schedule_that_says_nothing_waits_as_long_as_the_setting(settings, tmp_path):
    silent = parsed_schedule(MORNING, settings, tmp_path)
    blank = parsed_schedule({**MORNING, "approval_ttl_seconds": None}, settings, tmp_path)

    assert silent.approval_ttl_seconds is None and blank.approval_ttl_seconds is None
    assert silent.to_dict()["approval_ttl_seconds"] is None


@pytest.mark.parametrize("value", [30, 43_201, 0, -60, "abc", "7200", True, 1.5])
def test_a_wait_that_is_not_whole_seconds_between_a_minute_and_half_a_day_is_refused(
    settings, tmp_path, value
):
    """A quoted number is refused too: YAML reads `"7200"` as text, and a text that reads
    as seconds in one place and fails in another is worse than one clear error."""
    with pytest.raises(ValueError, match="agent a: schedule morning"):
        parsed_schedule({**MORNING, "approval_ttl_seconds": value}, settings, tmp_path)


def test_the_telegram_block_may_say_how_long_its_approvals_wait(settings, tmp_path):
    block = {"token_env": "COACH_BOT_TOKEN", "chat_id": 42, "approval_ttl_seconds": 900}
    profile = parse_profile("a", tmp_path, {"telegram": block}, settings)

    assert profile.telegram is not None and profile.telegram.approval_ttl_seconds == 900
    assert profile.to_dict()["telegram"] == block


def test_a_telegram_block_without_the_key_reads_as_it_always_did(settings, tmp_path):
    block = {"token_env": "COACH_BOT_TOKEN", "chat_id": 42}
    profile = parse_profile("a", tmp_path, {"telegram": block}, settings)

    assert profile.telegram is not None and profile.telegram.approval_ttl_seconds is None
    assert profile.to_dict()["telegram"] == block


@pytest.mark.parametrize(
    "block",
    [
        {"chat_id": 42, "approval_ttl_seconds": 900},
        {"token_env": "T", "approval_ttl_seconds": 900},
        {"token_env": "T", "chat_id": 42, "approval_ttl_seconds": 900, "ttl": 900},
    ],
)
def test_the_new_key_does_not_loosen_what_a_telegram_block_needs(settings, tmp_path, block):
    with pytest.raises(ValueError):
        parse_profile("a", tmp_path, {"telegram": block}, settings)


def test_a_bad_telegram_wait_names_the_block_it_came_from(settings, tmp_path):
    block = {"token_env": "T", "chat_id": 42, "approval_ttl_seconds": 10}

    with pytest.raises(ValueError, match="agent a: telegram"):
        parse_profile("a", tmp_path, {"telegram": block}, settings)


def test_a_conversation_keeps_its_wait_and_reports_it(store: Store):
    conv = store.create(approval_ttl_seconds=7200)

    assert store.get(conv.id).approval_ttl_seconds == 7200
    assert conv.to_dict()["approval_ttl_seconds"] == 7200
    assert store.create().approval_ttl_seconds is None


def test_the_conversations_wait_wins_and_the_setting_fills_in(settings: Settings, store: Store):
    assert effective_ttl(store.create(approval_ttl_seconds=7200), settings) == 7200
    assert effective_ttl(store.create(), settings) == settings.approval_ttl_seconds


def test_an_older_database_gains_the_column_with_nothing_in_it(tmp_path: Path):
    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL,"
        " status TEXT NOT NULL,"
        " autonomous INTEGER NOT NULL DEFAULT 0, cost_cap_usd REAL NOT NULL DEFAULT 0,"
        " spent_usd REAL NOT NULL DEFAULT 0, unknown_cost_calls INTEGER NOT NULL DEFAULT 0,"
        " skills TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);"
        "INSERT INTO conversations VALUES ('c1','old','idle',0,0,0,0,'[]','t','t');"
    )
    conn.commit()
    conn.close()

    assert Store(path).get("c1").approval_ttl_seconds is None


@pytest.fixture
def crew(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, home


def test_editing_another_schedule_keeps_this_ones_wait(crew) -> None:
    """The editor sends the whole list back; a key it did not carry would be dropped from
    every row the person never touched."""
    client, home = crew
    rows = [{**MORNING, "approval_ttl_seconds": 7200}, EVENING]
    client.post("/api/agents", json={"agent_id": "coder", "profile": {"schedules": rows}})
    declared = client.get("/api/agents/coder").json()["declared"]["schedules"]
    assert [row["approval_ttl_seconds"] for row in declared] == [7200, None]

    declared[1] = {**declared[1], "name": "Buổi tối"}
    reply = client.patch("/api/agents/coder", json={"profile": {"schedules": declared}})

    assert reply.status_code == 200, reply.json()
    again = client.get("/api/agents/coder").json()["declared"]["schedules"]
    assert [(row["name"], row["approval_ttl_seconds"]) for row in again] == [
        ("morning", 7200),
        ("Buổi tối", None),
    ]
    written = read_raw(home / "agents" / "coder" / "agent.yaml")["schedules"]
    assert written[0]["approval_ttl_seconds"] == 7200


def test_changing_the_chat_id_keeps_the_telegram_wait(crew) -> None:
    client, home = crew
    block = {"token_env": "CODER_TTL_TEST_TOKEN", "chat_id": 42, "approval_ttl_seconds": 900}
    client.post("/api/agents", json={"agent_id": "coder", "profile": {"telegram": block}})
    read = client.get("/api/agents/coder").json()["telegram"]
    assert read == block

    moved = {**read, "chat_id": 43}
    reply = client.patch("/api/agents/coder", json={"profile": {"telegram": moved}})

    assert reply.status_code == 200, reply.json()
    assert client.get("/api/agents/coder").json()["telegram"] == {**block, "chat_id": 43}
    written = read_raw(home / "agents" / "coder" / "agent.yaml")["telegram"]
    assert written["approval_ttl_seconds"] == 900


def test_the_web_editor_and_the_server_agree_on_what_a_schedule_row_holds():
    """The editor refuses a row with a key it does not know, so a key only the server knew
    would make every agent that uses it uneditable from the web."""
    contract = (ROOT / "web" / "src" / "test" / "schedule-contract.ts").read_text()
    [listed] = re.findall(r"^const SCHEDULE_KEYS = new Set\(\[(.+)\]\);$", contract, re.M)

    assert set(re.findall(r'"([a-z_]+)"', listed)) == SCHEDULE_KEYS


def test_an_expired_approval_reads_as_a_refusal_that_changed_nothing():
    """The opening is the one every reader already treats as a refusal — the web thread and
    the Telegram reply both match on it — and the rest stops the model from reaching the
    same end by another tool while nobody is there to say no."""
    assert EXPIRED_TOOL.startswith("Người dùng đã TỪ CHỐI hành động này (hết hạn chờ duyệt")
    assert "chưa có gì thay đổi" in EXPIRED_TOOL
    assert "tương đương" in EXPIRED_TOOL
