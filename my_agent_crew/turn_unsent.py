"""What a chat is owed of a turn a restart cut.

The bot reads a turn as it runs and answers once, when the turn ends or stops for a person
(`turn_reply.py`). A restart takes that reader with the turn, and what it had read goes
unsent. The turn carried on is read from the cut, so its chat would get the end of an
answer whose beginning is only in the log. Here that beginning is read back from the log as
the events the lost reader had been handed, to go in front of the ones still to come.

It begins where the turn began, or where it last stopped for a person: the reply sent at a
stop said what the turn had written until then, and nothing is said twice.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from my_agent_crew.agent.events import AssistantMessageEvent, Event, ToolResultEvent
from my_agent_crew.store.db import Store
from my_agent_crew.store.message_models import StoredMessage
from my_agent_crew.store.runs import RunRecord


def _stopped_at(store: Store, conv_id: str, call_id: str, asked_in: int | None) -> bool:
    """Whether the turn stopped for a person at this call. Only a turn that stops opens a
    request, and a request belongs to the message whose call opened it: a model may send a
    call id again, and that new call is no stop."""
    request = store.approvals.find_for_call(conv_id, call_id)
    return request is not None and request.message_id == asked_in


def _as_read(stored: StoredMessage) -> Event:
    message = stored.message
    if message.role == "assistant":
        return AssistantMessageEvent(
            stored.id,
            message.content,
            [call.to_dict() for call in message.tool_calls],
            stored.provider,
            stored.model,
            stored.cost_usd,
            stored.prompt_tokens,
            stored.cached_tokens,
        )
    # Whether the call succeeded is not kept in the log, and no reply reads it.
    return ToolResultEvent(message.tool_call_id or "", message.name or "", True, message.content)


def unsent(store: Store, run: RunRecord) -> list[Event]:
    """What `run` said and what its tools answered that its chat was never sent, oldest
    first. A run from before runs knew where they began is owed nothing."""
    conv_id = run.conversation_id or ""
    if run.after_seq is None:
        return []
    asked: dict[str, int] = {}  # per call id, the message whose call still has no result
    since: list[StoredMessage] = []
    for stored in store.messages.of_run(conv_id, run.id, run.after_seq, run.started_at):
        message = stored.message
        if message.role == "assistant":
            asked.update((call.id, stored.id) for call in message.tool_calls)
        elif message.role == "tool":
            call_id = message.tool_call_id or ""
            if _stopped_at(store, conv_id, call_id, asked.pop(call_id, None)):
                since = []  # the next reader began at what became of the call
        else:
            continue  # what a person wrote while the turn ran is not the turn's to say
        since.append(stored)
    if any(_stopped_at(store, conv_id, call_id, at) for call_id, at in asked.items()):
        # Cut while a call a person had been asked about ran: the stop sent all of this.
        return []
    return [_as_read(stored) for stored in since]


async def after(owed: Sequence[Event], rest: AsyncIterator[Event]) -> AsyncIterator[Event]:
    """`owed`, then the events of `rest` as they come."""
    for event in owed:
        yield event
    async for event in rest:
        yield event
