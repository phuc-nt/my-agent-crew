"""Channels carry an agent's conversations beyond the web UI. A profile names the env
var holding the channel's secret; the server builds a channel only when that var is set,
so a machine without the token still runs every agent, only without the channel."""

from __future__ import annotations

import logging
from collections.abc import Mapping

import httpx

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.channels.telegram_api import TelegramApi
from my_agent_crew.channels.telegram_channel import TelegramChannel

__all__ = ["OFFSET_FILE", "TelegramApi", "TelegramChannel", "build_channels"]

logger = logging.getLogger(__name__)
OFFSET_FILE = "telegram.offset"


def build_channels(
    agents: Mapping[str, AgentDeps],
    hub: ActivityHub,
    client: httpx.AsyncClient,
    env: Mapping[str, str],
) -> dict[str, TelegramChannel]:
    channels: dict[str, TelegramChannel] = {}
    for agent_id, deps in agents.items():
        config = deps.agent.telegram
        if config is None:
            continue
        token = env.get(config.token_env)
        if not token:
            logger.warning(
                "agent %s: env var %s is not set; telegram channel disabled",
                agent_id,
                config.token_env,
            )
            continue
        api = TelegramApi(token, client)
        offset_path = deps.agent.dir / OFFSET_FILE
        logger.info("agent %s: telegram channel enabled", agent_id)
        channels[agent_id] = TelegramChannel(deps, hub, api, config.chat_id, offset_path)
    return channels
