"""How long an approval waits for a person before it counts as refused.

The crew-wide setting suits a chat someone is looking at. A job that runs at night, or a
Telegram chat read a few times a day, may say how long its own approvals wait; the
conversation it opens keeps that number, so whatever answers later — the loop after a
restart, a delegated child, the parent waiting on it — reads the same wait.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from my_agent_crew import texts_approval as t

if TYPE_CHECKING:
    from my_agent_crew.config import Settings
    from my_agent_crew.store.models import Conversation

# A minute is the least a person can answer in; half a day covers a job that asks in the
# night and is read in the morning, and anything longer is an approval nobody will give.
MIN_TTL, MAX_TTL = 60, 43_200


def parse_approval_ttl(value: Any, where: str) -> int | None:
    """Whole seconds in range, or None when the key is absent. A quoted number and a bool
    are refused: YAML reads both as something other than seconds."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not MIN_TTL <= value <= MAX_TTL:
        raise ValueError(
            t.APPROVAL_TTL_INVALID.format(where=where, low=MIN_TTL, high=MAX_TTL, value=value)
        )
    return value


def effective_ttl(conversation: Conversation, settings: Settings) -> int:
    return conversation.approval_ttl_seconds or settings.approval_ttl_seconds
