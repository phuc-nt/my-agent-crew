"""The turn loop. State lives in the message log, so every entry point is the same
function: settle unfinished tool calls, then either finish or ask the model again."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    Event,
    HaltedEvent,
    TextDeltaEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from my_agent_crew.agent.prompt import active_skills, build_system_prompt
from my_agent_crew.config import Settings
from my_agent_crew.llm.provider import ProviderChain, ProviderError
from my_agent_crew.llm.types import Completion, Message, TextDelta
from my_agent_crew.skills import Skill
from my_agent_crew.store import Conversation, Store, StoredMessage
from my_agent_crew.store.approvals import DENIED, PENDING
from my_agent_crew.store.models import AWAITING_APPROVAL, IDLE
from my_agent_crew.texts import DENIED_TOOL
from my_agent_crew.tools import ToolRegistry


class ConversationBusy(Exception):
    """A new user message arrived while a tool call still waits for approval."""


@dataclass
class AgentDeps:
    settings: Settings
    chain: ProviderChain
    tools: ToolRegistry
    store: Store
    skills: list[Skill]


async def run_turn(deps: AgentDeps, conv_id: str, user_text: str | None) -> AsyncIterator[Event]:
    conv = deps.store.get(conv_id)
    if user_text is not None:
        if conv.status == AWAITING_APPROVAL:
            raise ConversationBusy(conv_id)
        deps.store.append(conv_id, Message(role="user", content=user_text))

    for _ in range(deps.settings.max_steps):
        async for event in _settle_tool_calls(deps, conv_id):
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
    deps: AgentDeps, conv_id: str, approval_id: str, approve: bool
) -> AsyncIterator[Event]:
    approval = deps.store.approvals.get(approval_id)
    if approval.conversation_id != conv_id or approval.status != PENDING:
        raise KeyError(approval_id)
    deps.store.approvals.resolve(approval_id, approve)
    deps.store.update(conv_id, status=IDLE)
    async for event in run_turn(deps, conv_id, None):
        yield event


async def _settle_tool_calls(deps: AgentDeps, conv_id: str) -> AsyncIterator[Event]:
    history = deps.store.history(conv_id)
    assistants = [m for m in history if m.message.role == "assistant"]
    if not assistants or not assistants[-1].message.tool_calls:
        return
    last = assistants[-1]
    answered = {m.message.tool_call_id for m in history if m.seq > last.seq}
    conv = deps.store.get(conv_id)
    for call in last.message.tool_calls:
        if call.id in answered:
            continue
        tool = deps.tools.get(call.name)
        if tool is not None and tool.requires_approval and not conv.autonomous:
            approval = deps.store.approvals.find_for_call(conv_id, call.id)
            if approval is None:
                approval = deps.store.approvals.create(conv_id, last.id, call)
                deps.store.update(conv_id, status=AWAITING_APPROVAL)
            if approval.status == PENDING:
                yield ApprovalRequiredEvent(
                    approval_id=approval.id,
                    tool_call_id=call.id,
                    name=call.name,
                    arguments=call.arguments,
                )
                return
            if approval.status == DENIED:
                deps.store.append(
                    conv_id,
                    Message(role="tool", content=DENIED_TOOL, tool_call_id=call.id, name=call.name),
                )
                yield ToolResultEvent(
                    tool_call_id=call.id, name=call.name, ok=False, output=DENIED_TOOL
                )
                continue
        yield ToolCallEvent(tool_call_id=call.id, name=call.name, arguments=call.arguments)
        result = await deps.tools.execute(call.name, call.arguments)
        deps.store.append(
            conv_id,
            Message(role="tool", content=result.output, tool_call_id=call.id, name=call.name),
        )
        yield ToolResultEvent(
            tool_call_id=call.id, name=call.name, ok=result.ok, output=result.output
        )


async def _complete(
    deps: AgentDeps, conv: Conversation, history: Sequence[StoredMessage]
) -> AsyncIterator[Event]:
    skills = active_skills(deps.skills, conv.skills)
    system = Message(
        role="system", content=build_system_prompt(deps.settings, skills, deps.tools.names())
    )
    messages = [system, *(m.message for m in history)]
    completion: Completion | None = None
    async for item in deps.chain.stream(messages, deps.tools.specs()):
        if isinstance(item, TextDelta):
            yield TextDeltaEvent(text=item.text)
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
