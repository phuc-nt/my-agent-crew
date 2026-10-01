"""A conversation's message log as `Store` offers it; `MessageStore` does the writing."""

from __future__ import annotations

from my_agent_crew.llm.types import Message
from my_agent_crew.store.message_models import StoredMessage
from my_agent_crew.store.stamps import now_iso


class MessageLog:
    """Mixed into `Store`, whose `messages` is the `MessageStore` on the shared connection."""

    def append(
        self,
        conv_id: str,
        message: Message,
        provider: str | None = None,
        model: str | None = None,
        cost_usd: float | None = None,
        **tokens: int | None,
    ) -> StoredMessage:
        """`tokens` are the message's prompt_tokens, completion_tokens, reasoning_tokens and
        cached_tokens, each None when the provider did not report it."""
        return self.messages.append(
            conv_id, message, now_iso(), provider, model, cost_usd, **tokens
        )

    def history(self, conv_id: str) -> list[StoredMessage]:
        return self.messages.history(conv_id)
