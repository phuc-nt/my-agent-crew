"""Which tool names an agent's `tools:` list can bring it, as the server tells an editor.

A start warns of a name the list holds and cannot bring (`test_tool_list_warnings.py`). The
same judge answers the editor, so it offers no name that would earn that warning and leaves
out none that would be honoured: a name is told as listable exactly when a list holding it
is told nothing. Each test starts a whole crew and asks over HTTP, as an editor does.
"""

import logging
import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from my_agent_crew.agents import DEFAULT_AGENT_ID
from my_agent_crew.config import load_settings
from my_agent_crew.server.app import create_app
from my_agent_crew.server.runtime_build import build_runtime
from my_agent_crew.server.tool_list_names import HONOURED, listable

# One of each agent the list is judged differently for.
CREW = {
    DEFAULT_AGENT_ID: {},
    "assistant": {},
    "worker": {"mode": "work"},
    "planner": {"delegates": ["assistant"]},
}
# Real names no tool built with an agent carries, and one nobody knows.
ELSEWHERE = ("delegate", "tool_script", "tool_search", "mcp__x__y", "made_up_tool")
NEVER_THE_LISTS = ("tool_script", "tool_search", "mcp__x__y")
WORK_ONLY = {"workspace_edit", "workspace_grep", "workspace_glob"}
PICTURES = {"MY_AGENT_VISION_ROUTES": "fake:echo"}
WARNED = re.compile(r"^agent (\S+): tools lists (?:unknown tool )?([^,\s]+)")


@pytest.fixture
def start(tmp_path: Path, caplog):
    """A crew started from the files given, a client to ask it, and what the start said of
    each agent's `tools:` list: the names it warned of, by agent."""
    clients = []

    def started(where: str, env: dict[str, str] | None = None, **agents):
        home = tmp_path / where
        for agent_id, raw in agents.items():
            # The master's file is the home's own; everyone else has a folder under `agents/`.
            directory = home if agent_id == DEFAULT_AGENT_ID else home / "agents" / agent_id
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "agent.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            settings = load_settings(
                env={"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo", **(env or {})}
            )
            runtime = build_runtime(settings)
        warned: dict[str, set[str]] = {agent_id: set() for agent_id in agents}
        for record in caplog.records:
            told = WARNED.match(record.getMessage())
            if told:
                warned[told[1]].add(told[2])
        client = TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1")
        client.__enter__()
        clients.append(client)
        return client, runtime, warned

    yield started
    for client in clients:
        client.__exit__(None, None, None)


def told(client, agent_id: str) -> list[str]:
    return client.get(f"/api/agents/{agent_id}").json()["listable_tools"]


@pytest.mark.parametrize("env", [PICTURES, {}], ids=["pictures can be read", "no picture route"])
def test_a_name_is_listable_exactly_when_a_list_holding_it_is_told_nothing(start, env) -> None:
    client, runtime, _ = start("plain", env, **CREW)
    held = {name for agent_id in CREW for name in runtime.deps_for(agent_id).tools.names()}
    names = sorted(held | set(ELSEWHERE) | WORK_ONLY | {"image_read"})
    open_lists = {agent_id: told(client, agent_id) for agent_id in CREW}

    listing = {agent_id: {**raw, "tools": names} for agent_id, raw in CREW.items()}
    client, runtime, warned = start("listing", env, **listing)

    # The one name a start says nothing of either way: a tool that needs a key the machine
    # may lack is a choice about the agent's role, and is not offered where it would not come.
    quiet = set() if env else {"image_read"}
    for agent_id in CREW:
        listed = told(client, agent_id)
        assert listed == sorted(set(listed)) == open_lists[agent_id], agent_id
        for name in names:
            says_nothing = name not in warned[agent_id]
            assert (name in listed) == (says_nothing and name not in quiet), (agent_id, name)
        # What the list is told it can bring, it brought.
        assert set(listed) <= set(runtime.deps_for(agent_id).tools.names()), agent_id
        assert not set(listed) & set(NEVER_THE_LISTS), agent_id
        assert "made_up_tool" in warned[agent_id]
    assert ("image_read" in open_lists["assistant"]) == bool(env)


def test_what_decides_a_name_is_the_agents_mode_and_whom_it_hands_work_to(start) -> None:
    client, _, _ = start("home", **CREW)
    listed = {agent_id: set(told(client, agent_id)) for agent_id in CREW}

    assert {"shell_run", "workspace_read", "ask_user"} <= set.intersection(*listed.values())
    assert "delegate" not in listed["assistant"]
    assert all("delegate" in listed[who] for who in (DEFAULT_AGENT_ID, "worker", "planner"))
    assert WORK_ONLY <= listed["worker"]
    assert all(not WORK_ONLY & listed[who] for who in (DEFAULT_AGENT_ID, "assistant", "planner"))


def test_what_a_list_could_bring_does_not_shrink_to_what_it_names(start) -> None:
    client, runtime, _ = start("home", narrow={"tools": ["shell_run"]}, open={})

    assert runtime.deps_for("narrow").tools.names() == ["shell_run"]
    assert told(client, "narrow") == told(client, "open")
    assert len(told(client, "narrow")) > 10


def test_the_list_of_agents_tells_the_same_names_as_one_agent(start) -> None:
    client, _, _ = start("home", **CREW)

    for row in client.get("/api/agents").json():
        assert row["listable_tools"] == told(client, row["id"])
        assert all(isinstance(name, str) for name in row["listable_tools"])
    assert {row["id"] for row in client.get("/api/agents").json()} == set(CREW)


def test_a_change_of_mode_is_told_by_the_save_and_by_the_next_read(start) -> None:
    client, _, _ = start("home", coder={}, helper={})
    brought_by_work = WORK_ONLY | {"delegate"}
    assert not brought_by_work & set(told(client, "coder"))

    saved = client.patch("/api/agents/coder", json={"profile": {"mode": "work"}})

    assert saved.status_code == 200, saved.text
    assert brought_by_work <= set(saved.json()["profile"]["listable_tools"])
    assert told(client, "coder") == saved.json()["profile"]["listable_tools"]
    assert not brought_by_work & set(told(client, "helper"))

    back = client.patch("/api/agents/coder", json={"profile": {"mode": "assistant"}})

    assert not brought_by_work & set(back.json()["profile"]["listable_tools"])
    assert told(client, "coder") == back.json()["profile"]["listable_tools"]


def test_a_change_of_delegates_is_told_by_the_save_and_by_the_next_read(start) -> None:
    client, _, _ = start("home", coder={}, helper={})
    before = told(client, "coder")
    assert "delegate" not in before

    saved = client.patch("/api/agents/coder", json={"profile": {"delegates": ["helper"]}})

    assert saved.status_code == 200, saved.text
    assert saved.json()["profile"]["listable_tools"] == sorted([*before, "delegate"])
    assert told(client, "coder") == saved.json()["profile"]["listable_tools"]

    back = client.patch("/api/agents/coder", json={"profile": {"delegates": None}})

    assert back.json()["profile"]["listable_tools"] == before == told(client, "coder")


def test_a_tool_handed_later_is_listable_only_while_the_list_is_honoured_for_it() -> None:
    def why(name: str) -> str | None:
        return {"delegate": HONOURED, "tool_script": "which the list does not decide"}.get(name)

    assert listable(["shell_run", "ask_user"], why) == ("ask_user", "delegate", "shell_run")
    assert listable(["shell_run"], lambda name: "which this agent is not given") == ("shell_run",)
    assert listable(["shell_run", "shell_run"], lambda name: None) == ("shell_run",)
