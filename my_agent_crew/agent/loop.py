"""The turn loop. State lives in the message log, so every entry point is the same
function: settle unfinished tool calls, then either finish or ask the model again."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field

from my_agent_crew.agent.child_wrap_up import nudge_to_conclude, wrap_up_due
from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    Event,
    HaltedEvent,
    ModelCallEvent,
    RouteFallbackEvent,
    TextDeltaEvent,
    ThinkingEvent,
)
from my_agent_crew.agent.prompt import turn_messages
from my_agent_crew.agent.reply_checks import blank_reply_event, with_dropped_attachments
from my_agent_crew.agent.tool_calls import settle_tool_calls
from my_agent_crew.agent.turn_context import (
    CHAT,
    set_turn_conversation,
    set_turn_source,
)
from my_agent_crew.agents.profile import AgentProfile, default_profile
from my_agent_crew.config import Settings
from my_agent_crew.llm.provider import ProviderChain, ProviderError
from my_agent_crew.llm.types import (
    Completion,
    Message,
    ReasoningDelta,
    RouteFailed,
    StreamStarted,
    TextDelta,
    ToolSpec,
)
from my_agent_crew.skills import Skill
from my_agent_crew.store import Conversation, Store, StoredMessage
from my_agent_crew.store.models import AWAITING_APPROVAL
from my_agent_crew.tools import ToolRegistry


class ConversationBusy(Exception):
    """A new user message arrived while a tool call still waits for approval."""


@dataclass
class AgentDeps:
    """Everything one agent needs for a turn. `settings` already carries the agent's own
    routes, cost cap and step limit; `profile` supplies persona and memory files."""

    settings: Settings
    chain: ProviderChain
    tools: ToolRegistry
    store: Store
    skills: list[Skill]
    profile: AgentProfile | None = None
    # The other agents on this machine, by id: the roster a delegating agent is shown.
    peers: Mapping[str, AgentProfile] = field(default_factory=dict)

    @property
    def agent(self) -> AgentProfile:
        return self.profile or default_profile(self.settings)


async def run_turn(
    deps: AgentDeps, conv_id: str, user_text: str | None, source: str = CHAT, depth: int = 0
) -> AsyncIterator[Event]:
    set_turn_source(source)
    set_turn_conversation(conv_id, depth)
    conv = deps.store.get(conv_id)
    if user_text is not None:
        if conv.status == AWAITING_APPROVAL:
            raise ConversationBusy(conv_id)
        deps.store.append(conv_id, Message(role="user", content=user_text))

    empty_replies = 0
    for _ in range(deps.settings.max_steps):
        async for event in settle_tool_calls(deps, conv_id):
            yield event
            if isinstance(event, ApprovalRequiredEvent):
                return
        history = deps.store.history(conv_id)
        last = history[-1].message
        if last.role == "assistant" and not last.tool_calls:
            if last.content.strip():
                conv = deps.store.get(conv_id)
                yield DoneEvent(
                    spent_usd=conv.spent_usd, unknown_cost_calls=conv.unknown_cost_calls
                )
                return
            blank = blank_reply_event(history[-1], empty_replies)
            if blank is not None:
                yield blank
                return
            empty_replies += 1
            # The blank turn is dropped from what the model sees: asking it to
            # continue from its own silence tends to produce more silence.
            history = history[:-1]
        conv = deps.store.get(conv_id)
        if conv.over_budget:
            yield HaltedEvent(reason="budget", spent_usd=conv.spent_usd)
            return
        # A delegated child near its soft cap is told to conclude and given no tools.
        tools: Sequence[ToolSpec] = deps.tools.specs()
        if wrap_up_due(conv, history, deps.settings.max_steps):
            history, tools = nudge_to_conclude(deps.store, conv, history), ()
        try:
            async for event in _complete(deps, conv, history, tools):
                yield event
        except ProviderError as exc:
            yield ErrorEvent(message=str(exc))
            return
    conv = deps.store.get(conv_id)
    yield HaltedEvent(reason="max_steps", spent_usd=conv.spent_usd)


async def _complete(
    deps: AgentDeps,
    conv: Conversation,
    history: Sequence[StoredMessage],
    tools: Sequence[ToolSpec],
) -> AsyncIterator[Event]:
    messages = turn_messages(deps, conv, history)
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
        else:
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
        tool_calls=[
            {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
            for tc in completion.message.tool_calls
        ],
        provider=completion.provider,
        model=completion.model,
        cost_usd=completion.usage.cost_usd,
        prompt_tokens=completion.usage.prompt_tokens,
        cached_tokens=completion.usage.cached_tokens,
    )
