"""Channel settings of a profile. A channel is how an agent reaches its user outside
the web UI; the profile names the env var that holds the secret, never the secret."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from my_agent_crew.agents.approval_ttl import parse_approval_ttl

TELEGRAM_REQUIRED = {"token_env", "chat_id"}
TELEGRAM_KEYS = TELEGRAM_REQUIRED | {"approval_ttl_seconds"}


@dataclass(frozen=True)
class TelegramConfig:
    token_env: str  # name of the env var holding the bot token
    chat_id: int  # the one chat the bot talks to; other chats are ignored
    # How long an approval in a conversation opened from this chat waits; None is the setting.
    approval_ttl_seconds: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """The wait only when set, so an agent that never uses it reads as it always did."""
        out: dict[str, Any] = {"token_env": self.token_env, "chat_id": self.chat_id}
        if self.approval_ttl_seconds is not None:
            out["approval_ttl_seconds"] = self.approval_ttl_seconds
        return out


def parse_telegram(raw: Any, agent_id: str) -> TelegramConfig:
    if not isinstance(raw, dict):
        raise ValueError(f"agent {agent_id}: telegram must be a mapping")
    unknown = set(raw) - TELEGRAM_KEYS
    if unknown:
        raise ValueError(f"agent {agent_id}: telegram has unknown keys {sorted(unknown)}")
    missing = TELEGRAM_REQUIRED - set(raw)
    if missing:
        raise ValueError(f"agent {agent_id}: telegram needs {sorted(missing)}")
    try:
        chat_id = int(raw["chat_id"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"agent {agent_id}: telegram chat_id must be an integer") from exc
    # A blank env name or an unset chat is a bot that can never start, and nothing
    # downstream reports it: the channel simply stays silent. Refusing here is the only
    # place the person still has the form open to fix it.
    token_env = str(raw["token_env"]).strip()
    if not token_env:
        raise ValueError(f"agent {agent_id}: telegram needs a token_env")
    if chat_id == 0:
        raise ValueError(f"agent {agent_id}: telegram needs a chat_id")
    ttl = parse_approval_ttl(raw.get("approval_ttl_seconds"), f"agent {agent_id}: telegram")
    return TelegramConfig(token_env=token_env, chat_id=chat_id, approval_ttl_seconds=ttl)
