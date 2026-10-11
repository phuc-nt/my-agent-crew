"""What the model reads of `tool_script`: how a script is written, and what one of this
agent's may call.

The agent's own tools are named with their parameters, and the MCP tools its owner opened
for scripts while lines are left; the rest a script finds for itself (`discovery.py`). What
only some agents' scripts do is said to those agents alone: calling the tools that change
things, asking a model, handing a task to another agent.
"""

from __future__ import annotations

from collections.abc import Sequence

from my_agent_crew import texts_script as t
from my_agent_crew import texts_script_delegate as handing
from my_agent_crew import texts_script_llm as words
from my_agent_crew.mcp.config import CODEMODE
from my_agent_crew.mcp.tools import McpTool
from my_agent_crew.script import limits
from my_agent_crew.script.signature import call_line, signature
from my_agent_crew.tools.registry import Tool

# Lines of the description that name a tool, the agent's own and its servers' together.
MAX_LISTED = 30


def description(
    builtins: Sequence[Tool],
    scripted: Sequence[McpTool],
    gated: bool,
    asks: bool = False,
    delegates: bool = False,
) -> str:
    """The agent's own tools come first, each with its parameters: what one is for is in its
    own declaration. Then the tools the owner opened for scripts, while lines are left. The
    model is only told how many more a script may call: past the last line, or never opened.
    `gated` for an agent told its scripts call the tools that change things as well, `asks`
    for one whose scripts can ask a model, `delegates` for one whose scripts hand tasks to
    other agents."""
    own = [f"- {call_line(tool)}" for tool in builtins[:MAX_LISTED]]
    opened = [tool for tool in scripted if tool.exposure == CODEMODE]
    served = [signature(tool) for tool in opened[: MAX_LISTED - len(own)]]
    left = len(builtins) + len(scripted) - len(own) - len(served)
    if left:
        (served if scripted else own).append(t.SCRIPT_MORE.format(count=left))
    told = (t.SCRIPT_DESCRIPTION_GATED if gated else t.SCRIPT_DESCRIPTION).format(
        calls=limits.MAX_CALLS,
        batch=limits.MAX_BATCH,
        example=t.SCRIPT_BATCH_EXAMPLE,
        builtins=t.SCRIPT_BUILTINS.format(lines="\n".join(own)) if own else "",
        mcp=t.SCRIPT_MCP.format(lines="\n".join(served)) if served else "",
    )
    if asks:
        told += words.LLM_DESCRIPTION.format(
            default=limits.LLM_SUMMARY_CHARS,
            most=limits.MAX_LLM_CALLS,
            chars=limits.MAX_LLM_TEXT_CHARS,
        )
    if delegates:
        told += handing.DELEGATE_DESCRIPTION.format(most=limits.MAX_PARALLEL_DELEGATE)
    return told
