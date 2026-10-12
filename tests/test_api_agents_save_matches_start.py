"""After a save, the crew that runs is the crew the next start would bring up.

Every route that rebuilds an agent, adds one or takes one away is followed here by one
question: read the home fresh, the way a start reads it, and set what runs beside it,
agent by agent and field by field. The fields are taken from the dataclass, so one added
later is held without a line of this file changed.

The home is one a start gives more than its files state: a kit of the crew and a kit of
an agent's own (a command, a skill folder and a hook each), a master whose file leaves
out its name, and the forms a person writes by hand that the start's reader and the
library a save writes with read two ways (`max_steps: 010`, `enabled: no`).
"""

from __future__ import annotations

import dataclasses
import json
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from my_agent_crew.agents import load_profiles
from my_agent_crew.agents.profile import AgentProfile
from my_agent_crew.config import ensure_home, load_settings
from my_agent_crew.server.app import create_app
from my_agent_crew.server.credential_catalog import KNOWN
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.server.runtime_build import build_runtime

HOOK = {
    "hooks": {
        "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "true"}]}]
    }
}
# No `name`: a start calls the master by the default's name, not by its id.
MASTER = """\
description: Giữ nhịp cho cả đội
max_steps: 010
schedules:
  - id: sang
    cron: "0 7 * * *"
    prompt: Chào buổi sáng
    enabled: no
"""
CODER = """\
name: Thợ mã
max_steps: 010
schedules:
  - id: don-dep
    cron: "30 2 * * *"
    prompt: Dọn dẹp
    enabled: no
"""
BRAVE = {"BRAVE_API_KEY": "brave-key-of-the-test"}


def kit(root: Path, command: str, skill: str) -> None:
    (root / "commands").mkdir(parents=True)
    (root / "commands" / f"{command}.md").write_text(f"Làm việc {command}.\n", encoding="utf-8")
    (root / "skills" / skill).mkdir(parents=True)
    (root / "skills" / skill / "SKILL.md").write_text(
        f"---\nname: {skill}\ndescription: Kỹ năng {skill}.\n---\nNội dung.\n", encoding="utf-8"
    )
    (root / "settings.json").write_text(json.dumps(HOOK), encoding="utf-8")


@pytest.fixture
def environ() -> Iterator[None]:
    saved = dict(os.environ)
    for name in [known.name for known in KNOWN] + ["MY_AGENT_ROUTES"]:
        os.environ.pop(name, None)
    yield
    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture
def home(tmp_path: Path, environ: None) -> Path:
    home = tmp_path / "home"
    (home / "agents" / "coder" / "workspace").mkdir(parents=True)
    (home / "config.yaml").write_text("routes:\n  - fake:echo\n", encoding="utf-8")
    (home / "agent.yaml").write_text(MASTER, encoding="utf-8")
    (home / "agents" / "coder" / "agent.yaml").write_text(CODER, encoding="utf-8")
    kit(home / ".claude", "standup", "notes")
    kit(home / "agents" / "coder" / ".claude", "review", "lint")
    return home


def started(home: Path, **saved: str) -> dict[str, AgentProfile]:
    """The crew a start would bring up from this home as it lies now. `saved` is what the
    start would find in its environment: a key the web saved is read back into it."""
    settings = ensure_home(load_settings(env={"MY_AGENT_HOME": str(home), **saved}))
    return {profile.id: profile for profile in load_profiles(settings)}


def unequal(ran: Any, would: Any, where: str) -> list[str]:
    """Every field two dataclasses differ in, by name; a dataclass inside, field by field."""
    found = []
    for field in dataclasses.fields(ran):
        mine, theirs = getattr(ran, field.name), getattr(would, field.name)
        name = f"{where}.{field.name}"
        if dataclasses.is_dataclass(mine) and type(mine) is type(theirs):
            found += unequal(mine, theirs, name)
        elif mine != theirs:
            found.append(f"{name}: runs with {mine!r}, a start gives {theirs!r}")
    return found


def apart(runtime: Runtime, home: Path, **saved: str) -> list[str]:
    """Where the crew that runs is not the crew a start would bring up. Nothing, when the
    two are one."""
    would = started(home, **saved)
    runs = {agent_id: deps.agent for agent_id, deps in runtime.agents.items()}
    found = []
    if runs.keys() != would.keys():
        found.append(f"crew: {sorted(runs)} run, a start gives {sorted(would)}")
    for agent_id in sorted(runs.keys() & would.keys()):
        found += unequal(runs[agent_id], would[agent_id], agent_id)
    return found


def done(reply: Any, *expected: int) -> None:
    assert reply.status_code in (expected or (200,)), reply.text


def edit(client: TestClient, agent_id: str, **profile: Any) -> None:
    done(client.patch(f"/api/agents/{agent_id}", json={"profile": profile}))


def master_edited(client: TestClient, home: Path) -> dict[str, str]:
    edit(client, "default", description="Giữ nhịp, và nhắc việc")
    return {}


def master_named_then_left_unnamed(client: TestClient, home: Path) -> dict[str, str]:
    edit(client, "default", name="Thư ký")
    edit(client, "default", name=None)
    return {}


def master_named(client: TestClient, home: Path) -> dict[str, str]:
    edit(client, "default", name="Thư ký")
    return {}


def agent_edited(client: TestClient, home: Path) -> dict[str, str]:
    edit(client, "coder", description="Viết mã và sửa lỗi")
    return {}


def agent_given_another_number(client: TestClient, home: Path) -> dict[str, str]:
    edit(client, "coder", max_steps=12)
    return {}


def agent_made(client: TestClient, home: Path) -> dict[str, str]:
    body = {"agent_id": "writer", "profile": {"name": "Người viết"}}
    done(client.post("/api/agents", json=body), 201)
    return {}


def agent_made_then_edited(client: TestClient, home: Path) -> dict[str, str]:
    agent_made(client, home)
    edit(client, "writer", description="Viết bài")
    return {}


def agent_removed(client: TestClient, home: Path) -> dict[str, str]:
    done(client.delete("/api/agents/coder"))
    return {}


def agent_made_then_removed(client: TestClient, home: Path) -> dict[str, str]:
    agent_made(client, home)
    done(client.delete("/api/agents/writer"))
    return {}


def persona_written(client: TestClient, home: Path) -> dict[str, str]:
    for agent_id in ("default", "coder"):
        done(client.put(f"/api/agents/{agent_id}/files/SOUL.md", json={"content": "Nói ngắn."}))
    return {}


def folder_put_in_by_hand(client: TestClient, home: Path) -> dict[str, str]:
    (home / "agents" / "tester" / "workspace").mkdir(parents=True)
    (home / "agents" / "tester" / "agent.yaml").write_text("name: Thợ thử\n", encoding="utf-8")
    kit(home / "agents" / "tester" / ".claude", "smoke", "probe")
    done(client.post("/api/agents/reload"))
    return {}


def template_installed(client: TestClient, home: Path) -> dict[str, str]:
    done(client.post("/api/agents/install", json={"template": "kongming"}), 201)
    return {}


def key_saved(client: TestClient, home: Path) -> dict[str, str]:
    (name, value), *_ = BRAVE.items()
    done(client.put(f"/api/credentials/{name}", json={"value": value}))
    return BRAVE


def key_saved_then_removed(client: TestClient, home: Path) -> dict[str, str]:
    key_saved(client, home)
    done(client.delete("/api/credentials/BRAVE_API_KEY"))
    return {}


def routes_saved(client: TestClient, home: Path) -> dict[str, str]:
    body = {"routes": [{"provider": "fake", "model": "second"}]}
    done(client.put("/api/connections/routes", json=body))
    return {}


def edit_after_a_key_and_the_routes(client: TestClient, home: Path) -> dict[str, str]:
    key_saved(client, home)
    routes_saved(client, home)
    edit(client, "coder", description="Viết mã")
    edit(client, "default", description="Giữ nhịp")
    return BRAVE


def key_and_routes_after_an_edit(client: TestClient, home: Path) -> dict[str, str]:
    edit(client, "coder", description="Viết mã")
    edit(client, "default", name="Thư ký")
    agent_made(client, home)
    routes_saved(client, home)
    return key_saved(client, home)


SAVES: list[Callable[[TestClient, Path], dict[str, str]]] = [
    master_edited,
    master_named,
    master_named_then_left_unnamed,
    agent_edited,
    agent_given_another_number,
    agent_made,
    agent_made_then_edited,
    agent_removed,
    agent_made_then_removed,
    persona_written,
    folder_put_in_by_hand,
    template_installed,
    key_saved,
    key_saved_then_removed,
    routes_saved,
    edit_after_a_key_and_the_routes,
    key_and_routes_after_an_edit,
]


def crew(home: Path) -> tuple[TestClient, Runtime]:
    runtime = build_runtime(load_settings(env={"MY_AGENT_HOME": str(home)}))
    return TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1"), runtime


def test_the_home_measured_on_gives_an_agent_more_than_its_file_states(home: Path) -> None:
    """Were the kits or the hand-written forms lost from this home, every comparison below
    would hold of two crews that have nothing a save could drop."""
    would = started(home)
    master, coder = would["default"], would["coder"]

    assert master.name == "Trợ lý"
    assert [command.name for command in master.commands] == ["standup"]
    assert sorted(command.name for command in coder.commands) == ["review", "standup"]
    assert (len(master.hooks), len(coder.hooks)) == (1, 2)
    assert master.kits == (home / ".claude",)
    assert coder.kits == (home / ".claude", home / "agents" / "coder" / ".claude")
    for kit_root in coder.kits:
        assert kit_root / "skills" in coder.skills_dirs
    for profile in (master, coder):
        assert profile.settings.max_steps == 8
        assert [row.enabled for row in profile.schedules] == [False]


def test_the_crew_a_start_brings_up_is_the_crew_a_start_would_bring_up(home: Path) -> None:
    client, runtime = crew(home)
    with client:
        assert apart(runtime, home) == []


def test_the_master_goes_by_the_name_its_file_gives_and_by_the_defaults_when_it_gives_none(
    home: Path,
) -> None:
    """Two crews that agree may both be wrong about the name, so it is read here as well."""
    client, runtime = crew(home)
    names = [runtime.default.agent.name]
    with client:
        for profile in ({"description": "Nhắc việc"}, {"name": "Thư ký"}, {"name": None}):
            edit(client, "default", **profile)
            names.append(runtime.default.agent.name)

    assert names == ["Trợ lý", "Trợ lý", "Thư ký", "Trợ lý"]
    assert started(home)["default"].name == "Trợ lý"


@pytest.mark.parametrize("save", SAVES, ids=lambda save: save.__name__.replace("_", " "))
def test_after_a_save_the_crew_that_runs_is_the_crew_a_start_would_bring_up(
    home: Path, save: Callable[[TestClient, Path], dict[str, str]]
) -> None:
    client, runtime = crew(home)
    with client:
        saved = save(client, home)

        assert apart(runtime, home, **saved) == []
