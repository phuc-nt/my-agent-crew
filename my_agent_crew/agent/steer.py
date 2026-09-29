"""Handing a running turn what the person sent while it ran with `/steer` or a kit command.

The loop takes them between steps: after the tool calls of the last step have results and
before the next model call reads the history, so the steer lands as a user message after a
complete step. A steer sent while the final answer streams is read the same way on the loop's
next pass, and the turn answers it rather than ending. A tool call already running is not
cut short: the steer waits for its result."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from my_agent_crew.agent.events import Event, SteerEvent
from my_agent_crew.agent.loop_guard import LoopGuard

if TYPE_CHECKING:  # the loop owns the deps; importing it back would be a cycle
    from my_agent_crew.agent.loop import AgentDeps


async def take_steers(deps: AgentDeps, conv_id: str, guard: LoopGuard) -> AsyncIterator[Event]:
    steered = deps.store.queue.take_steers(conv_id)
    if not steered:
        return
    # New words from the person are a new direction: repeats before them no longer count.
    guard.reset()
    yield SteerEvent(text="\n\n".join(item.text for item in steered), count=len(steered))
