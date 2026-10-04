"""The turn loop. State lives in the message log, so every entry point is the same
function: settle unfinished tool calls, then either finish or ask the model again."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field

from my_agent_crew import texts
from my_agent_crew.agent.child_wrap_up import nudge_to_conclude, wrap_up_due
from my_agent_crew.agent.events import (
    ApprovalRequiredEvent,
    AssistantMessageEvent,
    DoneEvent,
    ErrorEvent,
    Event,
    HaltedEvent,
    UserContextEvent,
)
from my_agent_crew.agent.loop_guard import HALT, OK, LoopGuard
from my_agent_crew.agent.model_stream import complete_step
from my_agent_crew.agent.payload_trim import turn_boundary
from my_agent_crew.agent.reply_checks import blank_reply_event
from my_agent_crew.agent.steer import take_steers
from my_agent_crew.agent.step_limit import out_of_steps
from my_agent_crew.agent.tool_calls import close_interrupted, refuse_unanswered, settle_tool_calls
from my_agent_crew.agent.turn_context import (
    CHAT,
    set_turn_conversation,
    set_turn_source,
)
from my_agent_crew.agents.profile import AgentProfile, default_profile
from my_agent_crew.config import Settings
from my_agent_crew.llm.provider import ProviderChain, ProviderError
from my_agent_crew.llm.types import Message, ToolSpec
from my_agent_crew.skills import Skill
from my_agent_crew.store import Store
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
    conv = deps.store.get(conv_id)
    set_turn_source(source)
    # A child picked up again after an approval or a restart arrives without the depth
    # its delegation gave it; the conversation still knows it is one level down.
    set_turn_conversation(conv_id, max(depth, 1) if conv.parent_call_id else depth)
    turn_start = turn_boundary(deps.store, conv_id)  # before this turn writes anything
    if user_text is not None:
        if conv.status == AWAITING_APPROVAL:
            raise ConversationBusy(conv_id)
        close_interrupted(deps.store, conv_id)
        stored = deps.store.append(
            conv_id, Message(role="user", content=user_text), note_source=source
        )
        if stored.context:
            yield UserContextEvent(stored.context)

    empty_replies = 0
    guard = LoopGuard()
    for _ in range(deps.settings.max_steps):
        async for event in settle_tool_calls(deps, conv_id):
            yield event
            if isinstance(event, ApprovalRequiredEvent):
                return
        async for event in take_steers(deps, conv_id, guard):
            yield event
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
        if guard.redirect_due:
            history = guard.redirect(deps.store, conv_id)
        # A delegated child near its soft cap is told to conclude and given no tools.
        tools: Sequence[ToolSpec] = deps.tools.specs()
        if wrap_up_due(conv, history, deps.settings.max_steps):
            history, tools = nudge_to_conclude(deps.store, conv, history), ()
        verdict = OK
        try:
            async for event in complete_step(deps, conv, history, tools, turn_start):
                yield event
                if isinstance(event, AssistantMessageEvent):
                    verdict = guard.observe(event.tool_calls)
        except ProviderError as exc:
            yield ErrorEvent(message=str(exc))
            return
        if verdict == HALT:  # the repeated calls stay unrun, each closed with a refusal
            async for event in refuse_unanswered(deps, conv_id, texts.LOOP_HALTED_TOOL):
                yield event
            yield HaltedEvent(reason="loop", spent_usd=deps.store.get(conv_id).spent_usd)
            return
    async for event in out_of_steps(deps, conv_id):
        yield event
