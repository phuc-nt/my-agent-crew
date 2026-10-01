"""The end of a turn that used every model call it was allowed.

The last call may still have answered: the turn is done, not halted. If it asked for tools
instead, those calls never ran, and each is closed with a refusal that says so; left open, a
later turn would close them as interrupted and tell the model it cannot know whether they ran."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from my_agent_crew import texts
from my_agent_crew.agent.events import DoneEvent, Event, HaltedEvent
from my_agent_crew.agent.tool_calls import refuse_unanswered

if TYPE_CHECKING:
    from my_agent_crew.agent.loop import AgentDeps


async def out_of_steps(deps: AgentDeps, conv_id: str) -> AsyncIterator[Event]:
    last = deps.store.history(conv_id)[-1].message
    if last.role == "assistant" and not last.tool_calls and last.content.strip():
        conv = deps.store.get(conv_id)
        yield DoneEvent(spent_usd=conv.spent_usd, unknown_cost_calls=conv.unknown_cost_calls)
        return
    async for event in refuse_unanswered(deps, conv_id, texts.STEPS_HALTED_TOOL):
        yield event
    yield HaltedEvent(reason="max_steps", spent_usd=deps.store.get(conv_id).spent_usd)
