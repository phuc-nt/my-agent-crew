"""Carrying out one tool call, and passing on what it says while it runs.

A call that is made alone runs as a task of its own, so the turn is free to send each
call a script makes inside it the moment that call ends. The task is the turn's: when the
turn is stopped or dropped mid-call, the task is cancelled and waited for, so a script's
process never outlives the turn that started it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import TYPE_CHECKING

from my_agent_crew.agent.nested_calls import set_nested_sink
from my_agent_crew.agent.tool_events import NestedCallEvent
from my_agent_crew.agent.turn_context import set_tool_call_id
from my_agent_crew.llm.tool_call_buffer import CUT_OFF
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.texts import TOOL_ARGS_CUT_OFF, TOOL_ARGS_INVALID
from my_agent_crew.tools.result import NestedCall, ToolResult

if TYPE_CHECKING:  # the loop owns the deps; importing it back would be a cycle
    from my_agent_crew.agent.loop import AgentDeps


async def execute(deps: AgentDeps, call: ToolCall) -> ToolResult:
    """Each call runs with its own id in context. A task copies the context it was made
    in, so a call run beside others reads its own id and not whichever one was set last. A
    call whose arguments never parsed is answered with where they broke instead of being run."""
    if call.invalid:
        template = TOOL_ARGS_CUT_OFF if call.invalid.startswith(CUT_OFF) else TOOL_ARGS_INVALID
        return ToolResult(ok=False, output=template.format(name=call.name, detail=call.invalid))
    set_tool_call_id(call.id)
    return await deps.tools.execute(call.name, call.arguments)


class CallRun:
    """One call being carried out. `events` yields a script's calls as they end and stops
    when the call is over; `result` is then what the call came to, or raises what it raised."""

    def __init__(self, deps: AgentDeps, call: ToolCall) -> None:
        self._call_id = call.id
        self._said: asyncio.Queue[NestedCall | None] = asyncio.Queue()
        self._task = asyncio.create_task(self._carry_out(deps, call))
        # Queued after everything the call said, since a task's callbacks run once it ended.
        self._task.add_done_callback(lambda _: self._said.put_nowait(None))

    async def _carry_out(self, deps: AgentDeps, call: ToolCall) -> ToolResult:
        set_nested_sink(self._said.put_nowait)
        return await execute(deps, call)

    async def events(self) -> AsyncIterator[NestedCallEvent]:
        index = 0
        try:
            while (nested := await self._said.get()) is not None:
                yield NestedCallEvent(self._call_id, index, asdict(nested))
                index += 1
        finally:
            if not self._task.done():
                self._task.cancel()
                await asyncio.wait([self._task])
                if not self._task.cancelled():
                    self._task.exception()  # read, so it is not reported as never looked at

    @property
    def result(self) -> ToolResult:
        return self._task.result()
