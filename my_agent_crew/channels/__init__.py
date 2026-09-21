"""Channels carry an agent's conversations beyond the web UI. A profile names the env
var holding the channel's secret; the server builds a channel only when that var is set,
so a machine without the token still runs every agent, only without the channel. Agents
that name the same env var share one bot: one poller, `@<agent id>` picks the agent."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from pathlib import Path

import httpx

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.channels.telegram_api import TelegramApi
from my_agent_crew.channels.telegram_channel import TelegramChannel
from my_agent_crew.channels.telegram_offset import read_offset, write_offset

__all__ = ["CHANNELS_DIR", "OFFSET_FILE", "TelegramApi", "TelegramChannel", "build_channels"]

logger = logging.getLogger(__name__)
OFFSET_FILE = "telegram.offset"
CHANNELS_DIR = "channels"


def build_channels(
    agents: Mapping[str, AgentDeps],
    hub: ActivityHub,
    client: httpx.AsyncClient,
    env: Mapping[str, str],
) -> dict[str, TelegramChannel]:
    """One channel per bot token, mapped from every agent it serves (so `deliver` finds
    the channel by agent id while the shared object is started once)."""
    bots: dict[str, dict[str, AgentDeps]] = {}
    for agent_id, deps in agents.items():
        config = deps.agent.telegram
        if config is None:
            continue
        if not env.get(config.token_env):
            logger.warning(
                "agent %s: env var %s is not set; telegram channel disabled",
                agent_id,
                config.token_env,
            )
            continue
        bots.setdefault(config.token_env, {})[agent_id] = deps
    channels: dict[str, TelegramChannel] = {}
    for token_env, members in bots.items():
        chat_ids = {deps.agent.telegram.chat_id for deps in members.values()}  # type: ignore[union-attr]
        if len(chat_ids) > 1:
            raise ValueError(
                f"agents {sorted(members)} share the bot {token_env} but not its chat_id"
            )
        api = TelegramApi(env[token_env], client)
        offset_path = resolve_offset_path(members, token_env)
        clock = next(iter(members.values())).settings.now  # the person's zone, not the box's
        channel = TelegramChannel(members, hub, api, chat_ids.pop(), offset_path, clock=clock)
        logger.info("telegram channel enabled for %s", ", ".join(members))
        for agent_id in members:
            channels[agent_id] = channel
    return channels


def resolve_offset_path(members: Mapping[str, AgentDeps], token_env: str) -> Path:
    """An agent alone keeps the offset next to its profile; a shared bot keeps it under
    `<home>/channels/`, seeded from the members' own files so nothing is replayed when a
    second agent joins a bot that already ran."""
    own = [deps.agent.dir / OFFSET_FILE for deps in members.values()]
    if len(own) == 1:
        return own[0]
    home = next(iter(members.values())).settings.home
    shared = home / CHANNELS_DIR / f"telegram-{token_env.lower()}.offset"
    if not shared.exists():
        offsets = [read_offset(path) for path in own]
        if any(offsets):
            write_offset(shared, max(offsets))
    return shared
