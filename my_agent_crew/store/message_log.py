"""A conversation's message log as `Store` offers it; `MessageStore` does the writing."""

from __future__ import annotations

from collections.abc import Callable

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
        *,
        note_source: str | None = None,
        request_id: str = "",
        turn_notes: Callable[[], str] | None = None,
        **tokens: int | None,
    ) -> StoredMessage:
        """`tokens` are the message's prompt_tokens, completion_tokens, reasoning_tokens and
        cached_tokens, each None when the provider did not report it. A person's message
        names the turn source it came from in `note_source`, so it is stored with its canvas
        note; the loop's own notes to the model pass none. `turn_notes` builds what a
        message that opens a turn tells of the agent's memory."""
        return self.messages.append(
            conv_id,
            message,
            now_iso(),
            provider,
            model,
            cost_usd,
            note_source=note_source,
            request_ids=(request_id,),
            turn_notes=turn_notes,
            **tokens,
        )

    def history(self, conv_id: str) -> list[StoredMessage]:
        return self.messages.history(conv_id)
