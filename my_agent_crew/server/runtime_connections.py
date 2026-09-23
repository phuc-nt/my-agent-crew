"""Re-reading the connections of a running crew: the keys, hosts and bot token that
were fixed at startup, applied again after the web changed them.

A change is applied in two steps. `prepare` builds the whole new crew — settings,
providers, every agent — from the environment as it would be, without touching the
running one; if that fails (a key removed that the only route needed), nothing has
been written and the change is refused. `commit` then swaps the result in. The new
providers go in as a new mapping rather than into the old one, because every chain
built so far holds the old mapping, and a turn already running must keep the providers
it started with instead of losing one halfway.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from my_agent_crew import texts
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents import load_profiles
from my_agent_crew.channels import build_channel
from my_agent_crew.config import Settings, with_secrets
from my_agent_crew.config_parse import Route
from my_agent_crew.server.agent_assembly import build_agent_deps, build_providers
from my_agent_crew.server.runtime import Runtime

# What the bot is built from: the master, its token's value and its chat.
ChannelKey = tuple[str, str, int] | None


@dataclass
class Prepared:
    settings: Settings
    providers: dict[str, Any]
    agents: dict[str, AgentDeps]


def channel_key(agents: Mapping[str, AgentDeps], env: Mapping[str, str]) -> ChannelKey:
    for agent_id, deps in agents.items():
        config = deps.agent.telegram
        if config is not None and deps.agent.is_master and env.get(config.token_env):
            return (agent_id, env[config.token_env], config.chat_id)
    return None


def prepare(rt: Runtime, env: Mapping[str, str], routes: Sequence[Route] | None = None) -> Prepared:
    """The crew rebuilt from `env` — and from `routes`, when the routes every agent falls
    back on are what changed — or the error that stops it being built. Only agents
    already running are rebuilt; installing new ones is not this path's business."""
    if rt.client is None:
        raise RuntimeError(texts.RUNTIME_CANNOT_GROW)
    settings = with_secrets(rt.settings, env)
    if routes is not None:
        settings = replace(settings, routes=tuple(routes))
    providers = build_providers(settings, rt.client, env)
    agents = {
        profile.id: build_agent_deps(profile, providers, rt.client, rt.store, settings.routes)
        for profile in load_profiles(settings)
        if profile.id in rt.agents
    }
    return Prepared(settings, providers, agents)


async def commit(rt: Runtime, prepared: Prepared, before: ChannelKey) -> None:
    """Swap a prepared crew in. `before` is what the bot was built from, taken before
    the environment changed; the bot is only rebuilt when that differs now."""
    peers = rt.default.peers if isinstance(rt.default.peers, dict) else {}
    rt.settings = prepared.settings
    rt.providers = prepared.providers
    for agent_id, deps in prepared.agents.items():
        deps.peers = peers
        rt.agents[agent_id] = deps
        peers[agent_id] = deps.profile
    rt.wire_delegation()
    await sync_channel(rt, before)


async def sync_channel(rt: Runtime, before: ChannelKey) -> None:
    """Bring the bot in line with the crew after agents were rebuilt. A changed master,
    token or chat means a new bot; anything else — a search key, a member's profile —
    only hands the running bot the new agents, so a message in the middle of being
    answered is not cut off by a change that has nothing to do with the chat."""
    if channel_key(rt.agents, os.environ) != before:
        await restart_channel(rt)
    elif rt.channel is not None:
        rt.channel.use_agents(rt.agents)


async def restart_channel(rt: Runtime) -> None:
    """Rebuild the master's bot from the profiles and environment as they are now. The
    new bot only polls if the old one was allowed to (a test app never polls), and that
    holds even when building it fails: the crew keeps whichever bot it has."""
    live = rt.channel_live
    try:
        await rt.stop_channel()
        if rt.client is None:
            rt.channel = None
            return
        rt.channel = build_channel(rt.agents, rt.hub, rt.client, os.environ)
        if rt.channel is not None:
            rt.channel.set_on_replaced(rt.summarize_replaced)
    finally:
        if live:
            rt.start_channel()
