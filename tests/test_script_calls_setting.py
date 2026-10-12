"""`script_calls`: whether the scripts of an agent may call the tools that change things.

It is read from the agent's own file and from nowhere else, so it is on only where somebody
wrote it; a value that is none of the three it knows stops the file from loading; and the
editor sets and clears it like any other key (`agents/profile_settings.py`). What the third
word, `none`, takes from an agent is in `test_script_switches.py`."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.agents.profile_yaml import load_yaml_profiles, parse_profile
from my_agent_crew.config import (
    SCRIPT_GATED,
    SCRIPT_NONE,
    SCRIPT_READ_ONLY,
    Settings,
    load_settings,
)
from my_agent_crew.script.scope import SCRIPT_TOOL
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime_build import build_runtime

REFUSED = "agent coach: script_calls must be none, read_only or gated"


def home_settings(home: Path) -> Settings:
    return load_settings(env={"MY_AGENT_HOME": str(home)})


def write_agent(home: Path, agent_id: str, body: str) -> None:
    (home / "agents" / agent_id).mkdir(parents=True)
    (home / "agents" / agent_id / "agent.yaml").write_text(body, encoding="utf-8")


def test_the_three_values_are_the_words_a_file_says() -> None:
    assert (SCRIPT_NONE, SCRIPT_READ_ONLY, SCRIPT_GATED) == ("none", "read_only", "gated")
    assert Settings.__dataclass_fields__["script_calls"].default == "read_only"


def test_scripts_only_read_unless_the_agents_own_file_says_otherwise(tmp_path: Path) -> None:
    write_agent(tmp_path, "keeper", "name: Keeper\nscript_calls: gated\n")
    write_agent(tmp_path, "reader", "name: Reader\nscript_calls: read_only\n")
    write_agent(tmp_path, "silent", "name: Silent\n")

    profiles = {p.id: p for p in load_yaml_profiles(home_settings(tmp_path))}

    assert profiles["keeper"].settings.script_calls == "gated"
    assert profiles["keeper"].to_dict()["script_calls"] == "gated"
    for left in ("reader", "silent", "default"):
        assert profiles[left].settings.script_calls == "read_only"
        assert profiles[left].to_dict()["script_calls"] == "read_only"


def test_the_default_agent_reads_it_from_its_own_file_and_hands_it_to_nobody(
    tmp_path: Path,
) -> None:
    (tmp_path / "agent.yaml").write_text("script_calls: gated\n", encoding="utf-8")
    write_agent(tmp_path, "silent", "name: Silent\n")

    profiles = {p.id: p for p in load_yaml_profiles(home_settings(tmp_path))}

    assert profiles["default"].settings.script_calls == "gated"
    assert profiles["default"].to_dict()["script_calls"] == "gated"
    assert profiles["silent"].settings.script_calls == "read_only"


@pytest.mark.parametrize(
    "raw",
    [{}, {"mode": "work"}, {"autonomous": True}, {"shell_network": False}],
    ids=["says nothing", "a work agent", "left to itself", "kept off the network"],
)
def test_it_is_never_taken_from_the_settings_an_agent_inherits(tmp_path: Path, raw) -> None:
    """Settings that say `gated` are what an agent would inherit if the key were read the
    way a cap is. Nothing but the key itself may turn it on."""
    inherited = replace(home_settings(tmp_path), script_calls="gated")

    made = parse_profile(
        "coach", tmp_path / "agents" / "coach", {"name": "Coach", **raw}, inherited
    )

    assert made.settings.script_calls == "read_only"
    assert made.to_dict()["script_calls"] == "read_only"


UNKNOWN = ["Gated", "GATED", " gated", "write", "all", "", "true", "None", "off", None, 1]


@pytest.mark.parametrize("value", [*UNKNOWN, ["gated"]], ids=repr)
def test_a_value_it_does_not_know_stops_the_file_from_loading(tmp_path: Path, value) -> None:
    """Read loosely, a slip in the one word would either turn the writes on where nobody
    meant to, or leave them off without a word where somebody did. The refusal names the
    three words and stops there."""
    raw = {"name": "Coach", "script_calls": value}
    with pytest.raises(ValueError) as refused:
        parse_profile("coach", tmp_path / "agents" / "coach", raw, home_settings(tmp_path))
    assert str(refused.value) == REFUSED


@pytest.mark.parametrize("value", [True, False], ids=repr)
def test_a_boolean_is_refused_with_the_three_words_like_any_other(tmp_path: Path, value) -> None:
    raw = {"name": "Coach", "script_calls": value}
    with pytest.raises(ValueError, match=REFUSED):
        parse_profile("coach", tmp_path / "agents" / "coach", raw, home_settings(tmp_path))


def test_a_file_with_a_wrong_value_is_refused_when_the_crew_is_read(tmp_path: Path) -> None:
    write_agent(tmp_path, "coach", "name: Coach\nscript_calls: writes\n")
    with pytest.raises(ValueError, match=REFUSED):
        load_yaml_profiles(home_settings(tmp_path))


@pytest.fixture
def crew(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        yield client, runtime, home


def manifest(home: Path, agent_id: str = "coder") -> str:
    return (home / "agents" / agent_id / "agent.yaml").read_text(encoding="utf-8")


def script_runs_again(runtime, agent_id: str = "coder") -> bool:
    """Whether a restart may run a cut script of the agent again: only one that reads."""
    tool = runtime.deps_for(agent_id).tools.get(SCRIPT_TOOL)
    assert tool is not None
    return tool.replay_safe


def test_the_editor_sets_and_clears_it_and_the_running_agent_follows(crew) -> None:
    client, runtime, home = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {}})
    assert client.get("/api/agents/coder").json()["script_calls"] == "read_only"
    assert script_runs_again(runtime) is True

    reply = client.patch("/api/agents/coder", json={"profile": {"script_calls": "gated"}})

    assert reply.status_code == 200
    assert reply.json()["profile"]["script_calls"] == "gated"
    assert client.get("/api/agents/coder").json()["script_calls"] == "gated"
    assert "script_calls: gated\n" in manifest(home)
    assert runtime.deps_for("coder").settings.script_calls == "gated"
    assert script_runs_again(runtime) is False

    reply = client.patch("/api/agents/coder", json={"profile": {"script_calls": None}})

    assert reply.status_code == 200 and reply.json()["profile"]["script_calls"] == "read_only"
    assert "script_calls" not in manifest(home)
    assert runtime.deps_for("coder").settings.script_calls == "read_only"
    assert script_runs_again(runtime) is True


def test_an_edit_about_something_else_keeps_it(crew) -> None:
    client, runtime, home = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {"script_calls": "gated"}})

    reply = client.patch("/api/agents/coder", json={"profile": {"description": "viết mã"}})

    assert reply.status_code == 200
    assert reply.json()["profile"]["script_calls"] == "gated"
    assert "script_calls: gated\n" in manifest(home)
    assert runtime.deps_for("coder").settings.script_calls == "gated"
    assert script_runs_again(runtime) is False


def test_a_new_agent_may_be_made_with_it(crew) -> None:
    client, runtime, home = crew

    reply = client.post(
        "/api/agents", json={"agent_id": "coder", "profile": {"script_calls": "gated"}}
    )

    assert reply.status_code == 201 and reply.json()["profile"]["script_calls"] == "gated"
    assert "script_calls: gated\n" in manifest(home)
    assert script_runs_again(runtime) is False


@pytest.mark.parametrize("value", ["write", "Gated", True, ["gated"]], ids=repr)
def test_the_editor_refuses_a_value_it_does_not_know_before_it_is_written(crew, value) -> None:
    client, runtime, home = crew
    client.post("/api/agents", json={"agent_id": "coder", "profile": {"script_calls": "gated"}})
    before = manifest(home)

    reply = client.patch("/api/agents/coder", json={"profile": {"script_calls": value}})

    assert reply.status_code == 422
    told = "agent coder: script_calls must be none, read_only or gated"
    # A boolean is told the same three words, and then which of them to write instead.
    assert reply.json()["detail"].startswith(told)
    assert (reply.json()["detail"] == told) is (value is not True)
    assert manifest(home) == before
    assert runtime.deps_for("coder").settings.script_calls == "gated"
    assert script_runs_again(runtime) is False


def test_a_new_agent_with_a_wrong_value_is_not_made(crew) -> None:
    client, runtime, home = crew

    reply = client.post(
        "/api/agents", json={"agent_id": "coder", "profile": {"script_calls": "write"}}
    )

    assert reply.status_code == 422
    assert reply.json()["detail"] == "agent coder: script_calls must be none, read_only or gated"
    assert not (home / "agents" / "coder" / "agent.yaml").exists()
    assert "coder" not in {p.id for p in runtime.profiles()}
