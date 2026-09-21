"""Channels carry the master's conversations beyond the web UI. The master's profile names
the env var holding the bot's secret; the server builds the channel only when that var is
set, so a machine without the token still runs every agent, only without the channel. The
chat is one more way to talk to the master, which delegates as it does from the web; a crew
member's scheduled brief still reaches the chat, delivered under the member's name."""

from __future__ import annotations

import logging
from collections.abc import Mapping

import httpx

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.channels.telegram_api import TelegramApi
from my_agent_crew.channels.telegram_channel import TelegramChannel

__all__ = ["OFFSET_FILE", "TelegramApi", "TelegramChannel", "build_channel"]

logger = logging.getLogger(__name__)
OFFSET_FILE = "telegram.offset"


def build_channel(
    agents: Mapping[str, AgentDeps],
    hub: ActivityHub,
    client: httpx.AsyncClient,
    env: Mapping[str, str],
) -> TelegramChannel | None:
    """The master's bot, or None when the master has no `telegram` block or its token is
    missing. A `telegram` block on any other profile is ignored with a warning: the person
    talks to one agent everywhere, and that agent hands the rest out."""
    channel: TelegramChannel | None = None
    for agent_id, deps in agents.items():
        config = deps.agent.telegram
        if config is None:
            continue
        if not deps.agent.is_master:
            logger.warning(
                "agent %s: telegram belongs to the master; its block is ignored", agent_id
            )
            continue
        if not env.get(config.token_env):
            logger.warning(
                "agent %s: env var %s is not set; telegram channel disabled",
                agent_id,
                config.token_env,
            )
            continue
        api = TelegramApi(env[config.token_env], client)
        offset_path = deps.agent.dir / OFFSET_FILE
        channel = TelegramChannel(
            agents, agent_id, hub, api, config.chat_id, offset_path, clock=deps.settings.now
        )
        logger.info("telegram channel enabled for %s", agent_id)
    return channel
