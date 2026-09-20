"""The turn loop. State lives in the message log, so every entry point is the same
function: settle unfinished tool calls, then either finish or ask the model again."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from my_agent_crew.agent.context_trim import trim_tool_outputs
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
from my_agent_crew.agent.prompt import active_skills, build_system_prompt
from my_agent_crew.agent.tool_calls import settle_tool_calls
from my_agent_crew.agent.turn_context import (
    CHAT,
    conversation_source,
    set_turn_conversation,
    set_turn_source,
)
from my_agent_crew.agents.context import bootstrap_sections
from my_agent_crew.agents.profile import AgentProfile, default_profile
from my_agent_crew.config import Settings
from my_agent_crew.llm.provider import ProviderChain, ProviderError
from my_agent_crew.llm.types import Completion, Message, RouteFailed, TextDelta
from my_agent_crew.memory.shared_chat import shared_chat_section
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
    # The other agents on this machine, by id, so a shared channel can name who spoke.
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

    for _ in range(deps.settings.max_steps):
        async for event in settle_tool_calls(deps, conv_id):
            yield event
            if isinstance(event, ApprovalRequiredEvent):
                return
        history = deps.store.history(conv_id)
        last = history[-1].message
        if last.role == "assistant" and not last.tool_calls:
            conv = deps.store.get(conv_id)
            yield DoneEvent(spent_usd=conv.spent_usd, unknown_cost_calls=conv.unknown_cost_calls)
            return
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
    skills = active_skills(deps.skills, conv.skills)
    active_names = {s.name for s in skills}
    index = [s for s in deps.skills if s.name not in active_names]
    profile = deps.agent
    previous = deps.store.previous_for_channel(conv.agent_id, conv.channel, conv.id)
    today = date.today()
    shared = shared_chat_section(
        deps.store, deps.peers, conv.channel, conv.agent_id, today.isoformat()
    )
    system = Message(
        role="system",
        content=build_system_prompt(
            deps.settings,
            skills,
            deps.tools.names(),
            sections=bootstrap_sections(
                profile,
                previous_summary=previous.summary if previous else "",
                extra_sections=[shared] if shared else [],
            ),
            name=profile.name,
            today=today.isoformat(),
            skill_index=index,
        ),
    )
    messages = [system, *trim_tool_outputs([m.message for m in history])]
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
