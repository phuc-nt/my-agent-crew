"""Agent profiles: the default agent from settings, `agents/<id>/agent.yaml` on top."""

from pathlib import Path

import pytest

from my_agent_crew.agents import DEFAULT_AGENT_ID, default_profile, load_profiles
from my_agent_crew.agents.profile_yaml import parse_profile
from my_agent_crew.config import Route, Settings


def test_default_profile_lives_in_home(settings: Settings):
    profile = default_profile(settings)
    assert profile.id == DEFAULT_AGENT_ID and profile.dir == settings.home
    assert profile.workspace == settings.workspace_dir
    assert profile.memory_file == settings.home / "MEMORY.md"
    assert profile.skills_dirs == (settings.skills_dir,)
    assert profile.settings is settings


def test_parse_profile_overrides_routes_and_limits_only(settings: Settings, tmp_path: Path):
    raw = {
        "name": "Coach",
        "description": "sức khoẻ",
        "routes": ["fake:echo", "scripted:m"],
        "workspace": "~/nonexistent-but-fine",
        "cost_cap_usd": 3,
        "max_steps": 4,
        "autonomous": True,
        "shell_ask_patterns": ["dd if="],
        "skills_dirs": ["../shared-skills"],
        "persona_files": ["SOUL.md"],
        "schedules": [
            {"id": "sync", "cron": "0 2 * * *", "command": "echo hi"},
            {"name": "brief", "every": "2h", "prompt": "tóm tắt", "skills": ["goodreads"]},
        ],
    }
    agent_dir = tmp_path / "agents" / "coach"
    profile = parse_profile("coach", agent_dir, raw, settings)
    assert profile.name == "Coach" and profile.description == "sức khoẻ"
    assert profile.settings.routes == (Route("fake", "echo"), Route("scripted", "m"))
    assert profile.settings.cost_cap_usd == 3 and profile.settings.max_steps == 4
    assert profile.settings.autonomous_default is True
    # Declaring the list replaces the defaults rather than adding to them.
    assert profile.settings.shell_ask_patterns == ("dd if=",)
    assert profile.to_dict()["shell_ask_patterns"] == ["dd if="]
    assert parse_profile("c2", agent_dir, {}, settings).settings.shell_ask_patterns == (
        settings.shell_ask_patterns
    )
    off = parse_profile("c3", agent_dir, {"shell_ask_patterns": []}, settings)
    assert off.settings.shell_ask_patterns == ()
    assert profile.settings.home == settings.home
    assert profile.workspace == Path("~/nonexistent-but-fine").expanduser().resolve()
    assert profile.skills_dirs == (agent_dir / "skills", (tmp_path / "agents" / "shared-skills"))
    assert profile.persona_files == ("SOUL.md",)
    assert [s.id for s in profile.schedules] == ["sync", "job-1"]
    assert profile.schedules[1].name == "brief" and profile.schedules[1].every == "2h"
    assert profile.schedules[0].skills == () and profile.schedules[1].skills == ("goodreads",)
    assert profile.schedules[1].to_dict()["skills"] == ["goodreads"]


@pytest.mark.parametrize(
    "raw",
    [
        {"bogus": 1},
        {"schedules": [{"id": "x", "prompt": "p"}]},
        {"schedules": [{"id": "x", "cron": "* * * * *", "every": "5m", "prompt": "p"}]},
        {"schedules": [{"id": "x", "cron": "* * * * *"}]},
        {"schedules": [{"id": "x", "cron": "* * * * *", "prompt": "p", "extra": 1}]},
    ],
)
def test_parse_profile_rejects_unknown_keys_and_ambiguous_schedules(settings, tmp_path, raw):
    with pytest.raises(ValueError):
        parse_profile("a", tmp_path, raw, settings)


def test_load_profiles_reads_agents_dir_sorted_and_reserves_default(settings: Settings):
    root = settings.home / "agents"
    for name in ("pong", "health-coach"):
        (root / name).mkdir(parents=True)
        (root / name / "agent.yaml").write_text(f"name: {name.title()}\n")
    (root / "no-manifest").mkdir()
    profiles = load_profiles(settings)
    assert [p.id for p in profiles] == ["default", "health-coach", "pong"]
    assert profiles[2].workspace == (root / "pong" / "workspace").resolve()
    (root / "default").mkdir()
    (root / "default" / "agent.yaml").write_text("name: x\n")
    with pytest.raises(ValueError):
        load_profiles(settings)


def test_to_dict_reports_only_persona_files_present(settings: Settings, tmp_path: Path):
    agent_dir = tmp_path / "agents" / "a"
    agent_dir.mkdir(parents=True)
    (agent_dir / "SOUL.md").write_text("tôi là a")
    data = parse_profile("a", agent_dir, {}, settings).to_dict()
    assert data["persona_files"] == ["SOUL.md"]
    assert data["routes"] == [{"provider": "scripted", "model": "m"}]
    assert data["schedules"] == []


def test_parse_profile_reads_a_telegram_block_and_reports_it(settings: Settings, tmp_path: Path):
    raw = {"telegram": {"token_env": "COACH_BOT_TOKEN", "chat_id": "42"}}
    profile = parse_profile("a", tmp_path, raw, settings)
    assert profile.telegram is not None
    assert (profile.telegram.token_env, profile.telegram.chat_id) == ("COACH_BOT_TOKEN", 42)
    assert profile.to_dict()["telegram"] == {"token_env": "COACH_BOT_TOKEN", "chat_id": 42}
    assert parse_profile("b", tmp_path, {}, settings).to_dict()["telegram"] is None


@pytest.mark.parametrize(
    "block",
    [
        "yes",
        {"token_env": "T"},
        {"token_env": "T", "chat_id": "abc"},
        {"token_env": "T", "chat_id": 1, "token": "never-inline"},
    ],
)
def test_parse_profile_rejects_malformed_telegram_blocks(settings, tmp_path, block):
    with pytest.raises(ValueError):
        parse_profile("a", tmp_path, {"telegram": block}, settings)
