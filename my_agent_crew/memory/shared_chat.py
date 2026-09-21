"""What the other agents said in this chat today.

On a shared Telegram bot several agents answer in one thread, so a person can say
something to Pong and then ask the coach about it. The coach holds its own conversation
and would otherwise see none of that. This lifts the last few lines the other agents
exchanged into the system prompt, read-only: it is context, not history the agent can
reply into, and nothing here is ever written back.

A private channel has only one agent, and the web has no channel at all, so both come
back empty and no section is added.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from my_agent_crew import texts
from my_agent_crew.agents.profile import AgentProfile
from my_agent_crew.store.db import Store

logger = logging.getLogger(__name__)

MAX_LINES = 10
MAX_LINE_CHARS = 300
MAX_SECTION_CHARS = 4000


def _line(name: str, role: str, text: str) -> str:
    body = " ".join(text.split())[:MAX_LINE_CHARS]
    return f"[{name}] {role}: {body}"


def shared_chat_section(
    store: Store,
    agents: Mapping[str, AgentProfile],
    channel: str,
    agent_id: str,
    since: str,
    limit: int = MAX_LINES,
) -> tuple[str, str] | None:
    """The `(title, body)` section for one agent's turn, or `None` when there is nothing.

    `since` is the UTC stamp the person's day began at (`clock.day_start_utc`): the store
    keeps UTC, and "today" is the person's, not the server's. `agents` maps an id to its
    profile so the lines carry names a person recognises; an agent that has since been
    removed keeps its id rather than disappearing.
    """
    if not channel:
        return None
    recent = store.messages.recent_on_channel(channel, since, agent_id, limit)
    if not recent:
        return None

    lines: list[str] = []
    budget = MAX_SECTION_CHARS
    for other_id, role, text in recent:
        profile = agents.get(other_id)
        line = _line(profile.name if profile else other_id, role, text)
        budget -= len(line) + 1
        if budget < 0:
            break
        lines.append(line)
    if not lines:
        return None

    # The prompt itself is not stored with the run, so this line is the only record that
    # the context was there. It counts lines and never prints what they said.
    logger.info("shared chat context: %d lines for %s", len(lines), agent_id)
    return texts.SHARED_CHAT_SECTION_TITLE, "\n".join(lines)
