"""The turn loop. State lives in the message log, so every entry point is the same
function: settle unfinished tool calls, then either finish or ask the model again."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field

from my_agent_crew import texts
from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    Event,
    HaltedEvent,
    RouteFallbackEvent,
    TextDeltaEvent,
)
from my_agent_crew.agent.prompt import turn_messages
from my_agent_crew.agent.tool_calls import settle_tool_calls
from my_agent_crew.agent.turn_context import (
    CHAT,
    conversation_source,
    set_turn_conversation,
    set_turn_source,
)
from my_agent_crew.agents.profile import AgentProfile, default_profile
from my_agent_crew.config import Settings
from my_agent_crew.llm.provider import ProviderChain, ProviderError
from my_agent_crew.llm.types import Completion, Message, RouteFailed, TextDelta
from my_agent_crew.skills import Skill
from my_agent_crew.store import Conversation, Store, StoredMessage
from my_agent_crew.store.approvals import PENDING
from my_agent_crew.store.models import AWAITING_APPROVAL, IDLE
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
            blank = _blank_reply_event(history[-1], empty_replies)
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
        try:
            async for event in _complete(deps, conv, history):
                yield event
        except ProviderError as exc:
            yield ErrorEvent(message=str(exc))
            return
    conv = deps.store.get(conv_id)
    yield HaltedEvent(reason="max_steps", spent_usd=conv.spent_usd)


def _blank_reply_event(blank: StoredMessage, already_retried: int) -> ErrorEvent | None:
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


async def resolve_approval(
    deps: AgentDeps, conv_id: str, approval_id: str, approve: bool, always: bool = False
) -> AsyncIterator[Event]:
    """`always` approves and also lets this tool run without asking for the rest of the
    conversation; the ask list for shell commands still applies on top."""
    approval = deps.store.approvals.get(approval_id)
    if approval.conversation_id != conv_id or approval.status != PENDING:
        raise KeyError(approval_id)
    deps.store.approvals.resolve(approval_id, approve)
    fields: dict[str, object] = {"status": IDLE}
    if approve and always:
        allowed = deps.store.get(conv_id).auto_approve
        if approval.tool_name not in allowed:
            fields["auto_approve"] = (*allowed, approval.tool_name)
    deps.store.update(conv_id, **fields)
    source = conversation_source(deps.store, conv_id)
    async for event in run_turn(deps, conv_id, None, source=source):
        yield event


async def _complete(
    deps: AgentDeps, conv: Conversation, history: Sequence[StoredMessage]
) -> AsyncIterator[Event]:
    messages = turn_messages(deps, conv, history)
    completion: Completion | None = None
    async for item in deps.chain.stream(messages, deps.tools.specs()):
        if isinstance(item, TextDelta):
            yield TextDeltaEvent(text=item.text)
        elif isinstance(item, RouteFailed):
            yield RouteFallbackEvent(provider=item.provider, model=item.model, error=item.error)
        else:
            completion = item
    if completion is None:
        raise ProviderError("stream ended without a completion")
    stored = deps.store.append(
        conv.id,
        completion.message,
        provider=completion.provider,
        model=completion.model,
        cost_usd=completion.usage.cost_usd,
        prompt_tokens=completion.usage.prompt_tokens,
        completion_tokens=completion.usage.completion_tokens,
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
    )
