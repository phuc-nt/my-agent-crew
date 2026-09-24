"""The master agent: read from the home's own manifest, handed every other agent as a
delegate unless it names its own, and told who its crew is on every turn."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.agents import DEFAULT_AGENT_ID, load_profiles
from my_agent_crew.agents.profile import ASSISTANT, WORK, default_profile
from my_agent_crew.agents.profile_yaml import MASTER_MANIFEST, load_master_profile
from my_agent_crew.agents.roster import DELEGATE_TOOL_NAME, crew_roster_section, delegate_targets
from my_agent_crew.config import Settings, load_settings
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.server import build_runtime
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store import Store
from my_agent_crew.tools.registry import ToolRegistry
from tests.conftest import collect, make_deps


def _write_agent(home: Path, agent_id: str, **raw) -> None:
    directory = home / "agents" / agent_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "agent.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")


def test_the_master_is_the_default_agent_and_says_so(settings: Settings):
    profile = default_profile(settings)
    assert profile.is_master and profile.to_dict()["is_master"] is True
    assert not replace(profile, id="coder").is_master


def test_a_manifest_in_the_home_shapes_the_master(settings: Settings):
    settings.home.mkdir(parents=True, exist_ok=True)
    (settings.home / MASTER_MANIFEST).write_text(
        "name: Sếp\ndescription: điều phối\nautonomous: true\ncost_cap_usd: 3\n",
        encoding="utf-8",
    )
    profile = load_master_profile(settings)
    assert profile.id == DEFAULT_AGENT_ID and profile.name == "Sếp"
    assert profile.description == "điều phối" and profile.is_master
    assert profile.settings.autonomous_default is True and profile.settings.cost_cap_usd == 3
    assert profile.dir == settings.home  # persona and memory stay where they always were


def test_without_a_manifest_the_master_is_the_plain_default(settings: Settings):
    assert load_master_profile(settings) == default_profile(settings)


def test_the_master_reaches_every_other_agent_unless_it_names_its_own(settings: Settings):
    settings.home.mkdir(parents=True, exist_ok=True)
    _write_agent(settings.home, "coder", name="Coder", mode=WORK)
    _write_agent(settings.home, "pong", name="Pong")
    profiles = {p.id: p for p in load_profiles(settings)}

    assert delegate_targets(profiles[DEFAULT_AGENT_ID], profiles) == ("coder", "pong")
    assert delegate_targets(profiles["coder"], profiles) == ()

    (settings.home / MASTER_MANIFEST).write_text("delegates: [pong]\n", encoding="utf-8")
    profiles = {p.id: p for p in load_profiles(settings)}
    assert delegate_targets(profiles[DEFAULT_AGENT_ID], profiles) == ("pong",)


def test_the_roster_names_each_delegate_with_what_it_does(settings: Settings):
    master = default_profile(settings)
    coder = replace(master, id="coder", name="Coder", mode=WORK, description="viết mã")
    pong = replace(master, id="pong", name="Pong")
    title, body = crew_roster_section(master, {"default": master, "coder": coder, "pong": pong})

    assert title == texts.CREW_ROSTER_TITLE
    assert "- coder — Coder (work): viết mã" in body
    assert f"- pong — Pong (assistant): {texts.CREW_ROSTER_NO_DESCRIPTION}" in body
    assert crew_roster_section(coder, {"coder": coder, "pong": pong}) is None


def test_the_roster_keeps_each_peer_workspace_to_itself(settings: Settings):
    """A master that knows where a peer keeps its files starts telling it which file to
    write, and invents the ones it does not know."""
    master = default_profile(settings)
    coach = replace(master, id="coach", name="Coach", workspace=Path("/srv/my-health-coach"))
    _, body = crew_roster_section(master, {"default": master, "coach": coach})
    assert "- coach — Coach" in body and "my-health-coach" not in body


def _crew(deps_factory, store: Store) -> Runtime:
    base = deps_factory([completion("ok"), completion("ok")])
    master = replace(base, tools=ToolRegistry([base.tools.get(n) for n in base.tools.names()]))
    helper = replace(
        base,
        profile=replace(base.profile, id="helper", name="Helper", mode=ASSISTANT),
        tools=ToolRegistry([base.tools.get(n) for n in base.tools.names()]),
    )
    agents: dict[str, AgentDeps] = {DEFAULT_AGENT_ID: master, "helper": helper}
    peers = {agent_id: deps.agent for agent_id, deps in agents.items()}
    for deps in agents.values():
        deps.peers = peers
    rt = Runtime(base.settings, store, agents, ActivityHub(store))
    rt.wire_delegation()
    return rt


async def test_the_master_holds_delegate_and_a_plain_assistant_does_not(deps_factory, store):
    rt = _crew(deps_factory, store)
    master = rt.deps_for(DEFAULT_AGENT_ID)
    spec = master.tools.get(DELEGATE_TOOL_NAME)
    assert spec is not None
    assert spec.parameters["properties"]["agent"]["enum"] == [DEFAULT_AGENT_ID, "helper"]
    assert DELEGATE_TOOL_NAME not in rt.deps_for("helper").tools.names()


async def test_the_master_reads_its_roster_in_the_system_prompt(deps_factory, store):
    rt = _crew(deps_factory, store)
    master = rt.deps_for(DEFAULT_AGENT_ID)
    conv = store.create(agent_id=DEFAULT_AGENT_ID)
    await collect(run_turn(master, conv.id, "chào"))

    provider: ScriptedProvider = master.chain.providers["scripted"]
    system = provider.requests[0].messages[0].content
    assert texts.CREW_ROSTER_TITLE in system and "- helper — Helper (assistant)" in system


async def test_a_child_turn_sees_no_roster_because_it_cannot_delegate(deps_factory, store):
    rt = _crew(deps_factory, store)
    child = rt.deps_for_child(DEFAULT_AGENT_ID)
    conv = store.create(agent_id=DEFAULT_AGENT_ID)
    await collect(run_turn(child, conv.id, "việc con", depth=1))

    provider: ScriptedProvider = child.chain.providers["scripted"]
    assert texts.CREW_ROSTER_TITLE not in provider.requests[0].messages[0].content


def test_agents_added_while_running_join_the_master_roster(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    _write_agent(home, "pong", name="Pong")
    env = {"MY_AGENT_HOME": str(home), "MY_AGENT_ROUTES": "fake:echo"}
    rt = build_runtime(load_settings(env=env))
    assert set(rt.agents) == {DEFAULT_AGENT_ID, "pong"}

    _write_agent(home, "coder", name="Coder", mode=WORK)
    added = rt.add_agents(load_profiles(rt.settings))

    assert added == ["coder"] and "coder" in rt.agents
    enum = rt.default.tools.get(DELEGATE_TOOL_NAME).parameters["properties"]["agent"]["enum"]
    assert enum == [DEFAULT_AGENT_ID, "pong", "coder"]
    assert rt.deps_for("coder").peers is rt.default.peers  # one shared map, not a copy
    assert rt.add_agents(load_profiles(rt.settings)) == []  # nothing new the second time


def test_a_runtime_built_around_one_agent_refuses_to_grow(settings: Settings, store: Store):
    rt = Runtime.single(make_deps(settings, store))
    with pytest.raises(RuntimeError):
        rt.add_agents([replace(rt.default.agent, id="coder")])
