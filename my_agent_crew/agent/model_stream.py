"""One model call of a turn: what the provider streams becomes the events a turn shows, and
the answer it ends with is stored before the event that announces it."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING

from my_agent_crew.agent.events import (
    AssistantMessageEvent,
    Event,
    ModelCallEvent,
    RouteFallbackEvent,
    TextDeltaEvent,
    ThinkingEvent,
)
from my_agent_crew.agent.prompt import turn_messages
from my_agent_crew.agent.reply_checks import with_dropped_attachments
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.llm.types import (
    Completion,
    ReasoningDelta,
    RouteFailed,
    StreamStarted,
    TextDelta,
    ToolSpec,
)
from my_agent_crew.store import Conversation, StoredMessage

if TYPE_CHECKING:  # the loop owns the deps; importing it back would be a cycle
    from my_agent_crew.agent.loop import AgentDeps


async def complete_step(
    deps: AgentDeps,
    conv: Conversation,
    history: Sequence[StoredMessage],
    tools: Sequence[ToolSpec],
    turn_start: int,
) -> AsyncIterator[Event]:
    messages = turn_messages(deps, conv, history, turn_start)
    completion: Completion | None = None
    thinking = False
    yield ModelCallEvent(stage="sent")
    async for item in deps.chain.stream(messages, tools):
        if isinstance(item, TextDelta):
            yield TextDeltaEvent(text=item.text)
        elif isinstance(item, ReasoningDelta):
            if not thinking:
                thinking = True
                yield ThinkingEvent()
        elif isinstance(item, StreamStarted):
            yield ModelCallEvent(stage="first_token")
        elif isinstance(item, RouteFailed):
            yield RouteFallbackEvent(provider=item.provider, model=item.model, error=item.error)
        elif isinstance(item, Completion):
            completion = item
    if completion is None:
        raise ProviderError("stream ended without a completion")
    completion = with_dropped_attachments(completion, history)
    stored = deps.store.append(
        conv.id,
        completion.message,
        provider=completion.provider,
        model=completion.model,
        cost_usd=completion.usage.cost_usd,
        prompt_tokens=completion.usage.prompt_tokens,
        completion_tokens=completion.usage.completion_tokens,
        reasoning_tokens=completion.usage.reasoning_tokens,
        cached_tokens=completion.usage.cached_tokens,
    )
    deps.store.add_spend(conv.id, completion.usage.cost_usd)
    yield AssistantMessageEvent(
        message_id=stored.id,
        content=completion.message.content,
        tool_calls=[tc.to_dict() for tc in completion.message.tool_calls],
        provider=completion.provider,
        model=completion.model,
        cost_usd=completion.usage.cost_usd,
        prompt_tokens=completion.usage.prompt_tokens,
        cached_tokens=completion.usage.cached_tokens,
    )
