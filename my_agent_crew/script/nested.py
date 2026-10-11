"""The calls one script makes: which it may make, how each is carried out and counted, and
what is kept of it for the run card.

A tool's answer is the script's to cut down, so it is handed far more of one than a turn
would be: `RAW_LIMIT`. Past that the answer is cut at the limit, and where the agent can read
a kept output back (`tool_output_read`) the whole of it is kept under an id of its own and
the script is told the id and where to read on from. It reads on in segments as long as it
may hold, whatever the agent's own cap.

A call to a tool that changes things, which only the scripts of some agents may make, is put
to the approval gate first (`gate.py`), and is made in the order it was written.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from my_agent_crew import texts_script as t
from my_agent_crew.activity.step_previews import argument_preview, preview
from my_agent_crew.agent.nested_calls import nested_budget, note_nested_call
from my_agent_crew.agent.turn_context import tool_call_id, turn_conversation_id
from my_agent_crew.script.discovery import discover
from my_agent_crew.script.limits import MAX_PARALLEL, RAW_LIMIT
from my_agent_crew.script.replies import Answer, Calls
from my_agent_crew.script.scope import callable_tools, only_reads, unknown_tool, why_not
from my_agent_crew.script.signature import call_line, misfits
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.tools.output_read import reading_up_to
from my_agent_crew.tools.output_shaping import shape_output
from my_agent_crew.tools.output_spill import MAX_SPILL_BYTES, READ_TOOL
from my_agent_crew.tools.registry import Tool, ToolRegistry
from my_agent_crew.tools.result import NestedCall, ToolResult

logger = logging.getLogger(__name__)
# One call put to the approval gate: None to let it run, or the refusal the script ends on.
Gate = Callable[[str, dict[str, Any]], str | None]


@dataclass
class ScriptRun:
    """One script's calls: what it may reach, and what it made."""

    held: ToolRegistry
    # Set for an agent whose scripts may also call the tools that change things: each such
    # call is put to it before any call of its batch runs.
    gate: Gate | None = None
    # The characters of tool answers the script was handed.
    received: int = 0
    # The calls asked for so far. Each is numbered as it was written: an answer kept whole
    # is kept under its number, and so is the call once it ended.
    made: int = 0
    _ended: dict[int, NestedCall] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.gated = self.gate is not None
        # Taken whole up to what can be kept, and cut for the script here (`_fit`).
        tools = callable_tools(self.held, self.gated)
        self.allowed = ToolRegistry(tools, MAX_SPILL_BYTES, self.held.hooks)

    @property
    def calls(self) -> list[NestedCall]:
        """The calls that ended, as the script wrote them, whichever ended first. Each is
        kept the moment it ends: a script cut short mid-batch still made the calls it made."""
        return [self._ended[number] for number in sorted(self._ended)]

    def lookup(self, kind: str, arguments: dict[str, Any]) -> Any:
        return discover(self.held, kind, arguments, self.gated)

    def _refusal(self, tool: Tool | None, arguments: dict[str, Any]) -> str | None:
        """Why the script may not make a call, known before any is made: the tool is not a
        script's to call, or it changes things and the approval gate would not let this
        call run without a person."""
        if tool is None:
            return None
        refusal = why_not(tool, self.gated)
        if refusal is None and self.gate is not None and not only_reads(tool):
            refusal = self.gate(tool.name, arguments)
        return refusal

    async def answer(self, name: str, arguments: dict[str, Any]) -> Answer:
        return (await self.answer_many([(name, arguments)]))[0]

    async def answer_many(self, calls: Calls) -> list[Answer]:
        """The calls of a batch made side by side, at most `MAX_PARALLEL` at a time, and
        answered in the order given. One call the script may not make ends the script, so
        then none is made: every call is answered all the same, the one that is refused
        with the reason and the rest as not made. So does a call past what the scripts
        of the turn may make between them: a batch that does not fit whole is not made.
        A batch with a call that changes things is made one call at a time, as written:
        what one such call leaves behind the next may count on."""
        tools = [self.held.get(name) for name, _ in calls]
        refusals = [
            self._refusal(tool, arguments)
            for tool, (_, arguments) in zip(tools, calls, strict=True)
        ]
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
        room = asyncio.Semaphore(MAX_PARALLEL)

        async def one(
            tool: Tool | None, name: str, arguments: dict[str, Any], number: int
        ) -> Answer:
            if tool is None:
                # A slip of the script's, and one it can catch: the name it meant is likely near.
                return Answer(False, unknown_tool(name, callable_tools(self.held, self.gated)))
            async with room:
                return await self._execute(tool, name, arguments, number)

        numbers = []  # given as written, before any call begins
        for tool in tools:
            self.made += tool is not None
            numbers.append(self.made)
        asked = list(zip(tools, calls, numbers, strict=True))
        if any(tool is not None and not only_reads(tool) for tool in tools):
            return [
                await one(tool, name, arguments, number)
                for tool, (name, arguments), number in asked
            ]
        async with asyncio.TaskGroup() as group:
            runs = [
                group.create_task(one(tool, name, arguments, number))
                for tool, (name, arguments), number in asked
            ]
        return [run.result() for run in runs]

    def _fit(self, result: ToolResult, number: int) -> str:
        """An answer the script can hold. One too long is cut at `RAW_LIMIT`; when the agent
        can read a kept output back, all of it is kept first, under the script's own call
        id and this call's number, and the script is told how to read on. What reading
        back answers was sized to fit (`_execute`), so it is never kept as another."""
        text = result.output
        if len(text) <= RAW_LIMIT:
            return text
        spill, script_id = self.held.spill, tool_call_id()
        kept_as = f"{script_id}.{number}"
        if (
            result.ok
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
        try:
            with reading_up_to(RAW_LIMIT):  # a kept answer read back comes in what fits here
                result = await self.allowed.execute(name, arguments)
            output = self._fit(result, number)
        except Exception as exc:  # what broke around one call fails that call, not the script
            logger.exception("a script's call of %s crashed", name)
            output = TOOL_FAILED.format(error=type(exc).__name__)
            result = ToolResult(ok=False, output=output)
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
            gated=not only_reads(tool),
        )
        self._ended[number] = nested
        note_nested_call(nested)  # shown as it ends, though the script has not
        return Answer(result.ok, output)
