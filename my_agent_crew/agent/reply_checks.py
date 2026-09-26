"""Two looks at a reply before the loop trusts it: is it a reply at all, and did it keep
the files a delegated child sent along."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from my_agent_crew import texts
from my_agent_crew.agent.events import ErrorEvent
from my_agent_crew.llm.types import Completion
from my_agent_crew.store import StoredMessage
from my_agent_crew.tools.delegate_attachments import dropped_attachments


def blank_reply_event(blank: StoredMessage, already_retried: int) -> ErrorEvent | None:
    """A reply with neither text nor a tool call is not a finished turn, it is a
    provider that returned nothing — ending there leaves the user looking at their own
    message with no sign anything happened. One more attempt usually gets a real
    answer; twice in a row is a fault worth naming, since the call was billed either
    way. `None` means retry."""
    if already_retried < 1:
        return None
    return ErrorEvent(
        message=texts.BLANK_COMPLETION.format(
            provider=blank.provider or "?", model=blank.model or "?"
        )
    )


def with_dropped_attachments(
    completion: Completion, history: Sequence[StoredMessage]
) -> Completion:
    """A final reply that retold a delegated answer gets back the charts and files the
    retelling left out, so they reach the person on the web and on Telegram alike."""
    message = completion.message
    if message.tool_calls or not message.content.strip():
        return completion
    missing = dropped_attachments(history, message.content)
    if not missing:
        return completion
    content = message.content.rstrip() + "\n\n" + "\n".join(missing)
    return replace(completion, message=replace(message, content=content))
