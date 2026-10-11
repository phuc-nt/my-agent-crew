"""The calls one script makes: which it may make, how each is carried out and counted, and
what is kept of it for the run card.

A tool's answer is the script's to cut down, so it is handed far more of one than a turn
would be: `RAW_LIMIT`. Past that the answer is cut at the limit, and where the agent can read
a kept output back (`tool_output_read`) the whole of it is kept under an id of its own and
the script is told the id and where to read on from.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from my_agent_crew import texts_script as t
from my_agent_crew.activity.step_previews import argument_preview, preview
from my_agent_crew.agent.nested_calls import nested_budget, note_nested_call
from my_agent_crew.agent.turn_context import tool_call_id, turn_conversation_id
from my_agent_crew.script.discovery import discover
from my_agent_crew.script.limits import MAX_PARALLEL, RAW_LIMIT
from my_agent_crew.script.replies import Answer, Calls
from my_agent_crew.script.scope import callable_tools, unknown_tool, why_not
from my_agent_crew.script.signature import call_line, misfits
from my_agent_crew.tools.output_shaping import shape_output
from my_agent_crew.tools.output_spill import MAX_SPILL_BYTES, READ_TOOL
from my_agent_crew.tools.registry import Tool, ToolRegistry
from my_agent_crew.tools.result import NestedCall, ToolResult


@dataclass
class ScriptRun:
    """One script's calls: what it may reach, and what it made."""

    held: ToolRegistry
    # The characters of tool answers the script was handed.
    received: int = 0
    # The calls asked for so far. Each is numbered as it was written: an answer kept whole
    # is kept under its number, and so is the call once it ended.
    made: int = 0
    _ended: dict[int, NestedCall] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Taken whole up to what can be kept, and cut for the script here (`_fit`).
        self.allowed = ToolRegistry(callable_tools(self.held), MAX_SPILL_BYTES, self.held.hooks)

    @property
    def calls(self) -> list[NestedCall]:
        """The calls that ended, as the script wrote them, whichever ended first. Each is
        kept the moment it ends: a script cut short mid-batch still made the calls it made."""
        return [self._ended[number] for number in sorted(self._ended)]

    def lookup(self, kind: str, arguments: dict[str, Any]) -> Any:
        return discover(self.held, kind, arguments)

    async def answer(self, name: str, arguments: dict[str, Any]) -> Answer:
        return (await self.answer_many([(name, arguments)]))[0]

    async def answer_many(self, calls: Calls) -> list[Answer]:
        """The calls of a batch made side by side, at most `MAX_PARALLEL` at a time, and
        answered in the order given. One call the script may not make ends the script, so
        then none is made: every call is answered all the same, the one that is refused
        with the reason and the rest as not made. So does a call past what the scripts
        of the turn may make between them: a batch that does not fit whole is not made."""
        tools = [self.held.get(name) for name, _ in calls]
        refusals = [None if tool is None else why_not(tool) for tool in tools]
        if any(refusal is not None for refusal in refusals):
            return [
                Answer(False, t.SCRIPT_BATCH_NOT_RUN)
                if refusal is None
                else Answer(False, refusal, halt=True)
                for refusal in refusals
            ]
        budget, known = nested_budget(), sum(tool is not None for tool in tools)
        if budget is not None and not budget.take(known):
            spent = t.SCRIPT_TURN_CALLS_SPENT.format(most=budget.limit)
            return [Answer(False, spent, halt=True) for _ in calls]
        gate = asyncio.Semaphore(MAX_PARALLEL)

        async def one(
            tool: Tool | None, name: str, arguments: dict[str, Any], number: int
        ) -> Answer:
            if tool is None:
                # A slip of the script's, and one it can catch: the name it meant is likely near.
                return Answer(False, unknown_tool(name, callable_tools(self.held)))
            async with gate:
                return await self._execute(tool, name, arguments, number)

        numbers = []  # given as written, before any call begins
        for tool in tools:
            self.made += tool is not None
            numbers.append(self.made)
        async with asyncio.TaskGroup() as group:
            runs = [
                group.create_task(one(tool, name, arguments, number))
                for tool, (name, arguments), number in zip(tools, calls, numbers, strict=True)
            ]
        return [run.result() for run in runs]

    def _fit(self, name: str, result: ToolResult, number: int) -> str:
        """An answer the script can hold. One too long is cut at `RAW_LIMIT`; when the agent
        can read a kept output back, all of it is kept first, under the script's own call
        id and this call's number, and the script is told how to read on. What reading
        back answers is never kept again, or one long answer would be kept without end."""
        text = result.output
        if len(text) <= RAW_LIMIT:
            return text
        spill, script_id = self.held.spill, tool_call_id()
        kept_as = f"{script_id}.{number}"
        if (
            result.ok
            and name != READ_TOOL
            and spill is not None
            and self.allowed.get(READ_TOOL) is not None
            and script_id  # outside a turn there is no call to keep it under
            and spill.write(turn_conversation_id(), kept_as, text)
        ):
            left = len(text) - RAW_LIMIT
            return text[:RAW_LIMIT] + t.SCRIPT_ANSWER_KEPT.format(
                left=left, id=kept_as, offset=RAW_LIMIT
            )
        return shape_output(text, RAW_LIMIT).text

    async def _execute(
        self, tool: Tool, name: str, arguments: dict[str, Any], number: int
    ) -> Answer:
        # Timed from here, when the call begins, and not from when it was asked for.
        started = time.monotonic()
        result = await self.allowed.execute(name, arguments)
        output = self._fit(name, result, number)
        if not result.ok and misfits(tool, arguments):
            # The tool's own words for what went wrong stay; how it is called comes after.
            output = f"{output}\n{t.SCRIPT_CALL_LIKE.format(line=call_line(tool))}"
        self.received += len(output)
        nested = NestedCall(
            name=name,
            arguments=argument_preview(arguments),
            ok=result.ok,
            output=preview(output),
            ms=int((time.monotonic() - started) * 1000),
            cost_usd=result.cost_usd if result.metered else None,
            metered=result.metered,
        )
        self._ended[number] = nested
        note_nested_call(nested)  # shown as it ends, though the script has not
        return Answer(result.ok, output)
