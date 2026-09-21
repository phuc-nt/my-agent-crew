"""Making a `Runtime` out of a home directory: profiles read, deps built per agent, the
peer map shared, channels attached, delegation wired."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence

import httpx

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents import AgentProfile, load_profiles
from my_agent_crew.channels import build_channels
from my_agent_crew.config import Settings, ensure_home
from my_agent_crew.server.agent_assembly import build_agent_deps, build_providers
from my_agent_crew.server.runtime import PROVIDER_TIMEOUT_SECONDS, Runtime
from my_agent_crew.store import Store

__all__ = ["build_deps", "build_runtime", "check_delegates"]


def check_delegates(profiles: Sequence[AgentProfile]) -> None:
    """A profile pointing at an agent that does not exist would only fail mid-task, with
    the model left guessing why; it is a startup error instead."""
    known = {profile.id for profile in profiles}
    for profile in profiles:
        for name in profile.delegates:
            if name not in known:
                raise ValueError(
                    texts.DELEGATE_UNKNOWN_AGENT.format(agent_id=profile.id, target=name)
                )


def build_runtime(
    settings: Settings,
    client: httpx.AsyncClient | None = None,
    env: Mapping[str, str] | None = None,
) -> Runtime:
    """`env` is where channel tokens are read from (the process environment by default);
    settings never hold them, so a profile can be committed while its token stays out."""
    settings = ensure_home(settings)
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(PROVIDER_TIMEOUT_SECONDS))
    store = Store(settings.db_path)
    providers = build_providers(settings, client)
    profiles = load_profiles(settings)
    check_delegates(profiles)
    agents = {
        profile.id: build_agent_deps(profile, providers, client, store, settings.routes)
        for profile in profiles
    }
    peers = {agent_id: deps.agent for agent_id, deps in agents.items()}
    for deps in agents.values():
        deps.peers = peers  # every agent can name the others sharing its channel
    hub = ActivityHub(store)
    channels = build_channels(agents, hub, client, os.environ if env is None else env)
    runtime = Runtime(
        settings=settings,
        store=store,
        agents=agents,
        hub=hub,
        channels=channels,
        providers=providers,
        client=client,
    )
    runtime.wire_delegation()
    return runtime


def build_deps(settings: Settings, client: httpx.AsyncClient | None = None) -> AgentDeps:
    """The default agent's deps alone, for callers that only need one agent."""
    return build_runtime(settings, client).default
