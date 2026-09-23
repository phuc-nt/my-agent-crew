"""Re-reading the connections of a running crew: the keys, hosts and bot token that
were fixed at startup, applied again after the web changed them."""

from __future__ import annotations

import os

from my_agent_crew import texts
from my_agent_crew.agents import load_profiles
from my_agent_crew.channels import build_channel
from my_agent_crew.config import with_secrets
from my_agent_crew.server.agent_assembly import build_providers
from my_agent_crew.server.runtime import Runtime


async def restart_channel(rt: Runtime) -> None:
    """Rebuild the master's bot from the profiles and environment as they are now: a
    token saved or a chat changed from the web works without a restart. The new bot
    only starts polling if the old one was allowed to (a test app never polls)."""
    live = rt.channel_live
    await rt.stop_channel()
    if rt.client is None:
        rt.channel = None
        return
    rt.channel = build_channel(rt.agents, rt.hub, rt.client, os.environ)
    if rt.channel is not None:
        rt.channel.set_on_replaced(rt.summarize_replaced)
    if live:
        rt.start_channel()


async def reload_connections(rt: Runtime) -> None:
    """Apply what the environment holds now — keys, the firecrawl and ollama hosts, the
    bot token — to the running crew. Providers are rebuilt from the new keys and every
    agent after them, since routes and web tools are chosen at assembly and each
    profile's settings are derived from the global ones. Everything is read before
    anything is swapped, so a profile that fails to load leaves the crew as it was.
    A turn already running keeps the deps it started with."""
    if rt.client is None:
        raise RuntimeError(texts.RUNTIME_CANNOT_GROW)
    settings = with_secrets(rt.settings, os.environ)
    profiles = load_profiles(settings)
    providers = build_providers(settings, rt.client)
    rt.settings = settings
    rt.providers.clear()
    rt.providers.update(providers)
    for profile in profiles:
        if profile.id in rt.agents:
            rt.replace_agent(profile)
    await restart_channel(rt)
