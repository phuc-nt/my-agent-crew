"""An answer cut to what a script can hold, and kept whole where it can be read back.

A tool's answer is the script's to cut down, so it is handed far more of one than a turn
would be: `RAW_LIMIT`. Past that the answer is cut at the limit, and where the agent can read
a kept output back (`tool_output_read`) the whole of it is kept under an id of its own and
the script is told the id and where to read on from. It reads on in segments as long as it
may hold, whatever the agent's own cap.
"""

from __future__ import annotations

from my_agent_crew import texts_script as t
from my_agent_crew.agent.turn_context import tool_call_id, turn_conversation_id
from my_agent_crew.script.limits import RAW_LIMIT
from my_agent_crew.tools.output_shaping import shape_output
from my_agent_crew.tools.output_spill import READ_TOOL
from my_agent_crew.tools.registry import ToolRegistry
from my_agent_crew.tools.result import ToolResult


def fit(held: ToolRegistry, allowed: ToolRegistry, result: ToolResult, number: int) -> str:
    """An answer the script can hold, of a call it made of the tools `allowed` it, out of
    the ones the agent `held`. One too long is cut at `RAW_LIMIT`; when the agent can read a
    kept output back, all of it is kept first, under the script's own call id and this
    call's number, and the script is told how to read on. What reading back answers was
    sized to fit (`ScriptRun._execute`), so it is never kept as another."""
    text = result.output
    if len(text) <= RAW_LIMIT:
        return text
    spill, script_id = held.spill, tool_call_id()
    kept_as = f"{script_id}.{number}"
    if (
        result.ok
        and spill is not None
        and allowed.get(READ_TOOL) is not None
        and script_id  # outside a turn there is no call to keep it under
        and spill.write(turn_conversation_id(), kept_as, text)
    ):
        left = len(text) - RAW_LIMIT
        return text[:RAW_LIMIT] + t.SCRIPT_ANSWER_KEPT.format(
            left=left, id=kept_as, offset=RAW_LIMIT
        )
    return shape_output(text, RAW_LIMIT).text
