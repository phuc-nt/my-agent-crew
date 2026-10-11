"""Carrying out one tool call, and passing on what it says while it runs.

A call that is made alone runs as a task of its own, so the turn is free to send each
call a script makes inside it the moment that call ends. The task is the turn's: when the
turn is stopped or dropped mid-call, the task is cancelled and waited for, so a script's
process never outlives the turn that started it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable, Sequence
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
    from my_agent_crew.store import Store


async def execute(deps: AgentDeps, call: ToolCall) -> ToolResult:
    """Each call runs with its own id in context. A task copies the context it was made
    in, so a call run beside others reads its own id and not whichever one was set last. A
    call whose arguments never parsed is answered with where they broke instead of being run."""
    if call.invalid:
        template = TOOL_ARGS_CUT_OFF if call.invalid.startswith(CUT_OFF) else TOOL_ARGS_INVALID
        return ToolResult(ok=False, output=template.format(name=call.name, detail=call.invalid))
    set_tool_call_id(call.id)
    return await deps.tools.execute(call.name, call.arguments)


def charge_nested(store: Store, conv_id: str, calls: Iterable[NestedCall]) -> None:
    """A call a script made that paid a model is charged to the conversation like one the
    model made itself."""
    for nested in calls:
        if nested.metered:
            store.add_spend(conv_id, nested.cost_usd)


def not_yet_told(calls: Sequence[NestedCall], told: Sequence[NestedCall]) -> list[NestedCall]:
    """The calls of a script's result that were not told while it ran. Those were charged
    as they were told, and the result names them again in another order."""
    left = list(calls)
    for heard in told:
        if heard in left:
            left.remove(heard)
    return left


class CallRun:
    """One call being carried out. `events` yields a script's calls as they end and stops
    when the call is over; `result` is then what the call came to, or raises what it raised.

    Each call is charged to the conversation as it is told, where the run bills it too. A
    script a stopped turn cut short has no result to charge from, and the calls it made
    were paid for all the same."""

    def __init__(self, deps: AgentDeps, conv_id: str, call: ToolCall) -> None:
        self._store, self._conv_id, self._call_id = deps.store, conv_id, call.id
        self.told: list[NestedCall] = []
        self._said: asyncio.Queue[NestedCall | None] = asyncio.Queue()
        self._task = asyncio.create_task(self._carry_out(deps, call))
        # Queued after everything the call said, since a task's callbacks run once it ended.
        self._task.add_done_callback(lambda _: self._said.put_nowait(None))

    async def _carry_out(self, deps: AgentDeps, call: ToolCall) -> ToolResult:
        set_nested_sink(self._said.put_nowait)
        return await execute(deps, call)

    async def events(self) -> AsyncIterator[NestedCallEvent]:
        try:
            while (nested := await self._said.get()) is not None:
                charge_nested(self._store, self._conv_id, [nested])
                self.told.append(nested)
                yield NestedCallEvent(self._call_id, len(self.told) - 1, nested.to_dict())
        finally:
            if not self._task.done():
                self._task.cancel()
                await asyncio.wait([self._task])
                if not self._task.cancelled():
                    self._task.exception()  # read, so it is not reported as never looked at

    @property
    def result(self) -> ToolResult:
        return self._task.result()
