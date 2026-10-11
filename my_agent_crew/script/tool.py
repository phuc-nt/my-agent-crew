"""`tool_script`: a short script of the model's that calls the agent's read-only tools.

A turn that needs the same tool twenty times, or three lines out of a long answer, pays
for every call and every answer in context. Here the model writes that work as a script:
the script makes the calls, and only what it prints comes back.

A script may call a tool that only reads and asks nobody (`scope.py`): of the MCP tools every
one the owner listed under `read_only` that is not hidden, however far it is let in. How far
decides only whether the description below names it or the script finds it, with
`tools.search`. An agent holds the tool while it holds one such tool, of its own or a
server's, whatever its `tools:` list and its mode say (`hand_script`). Anything that writes,
or stops for a person, is called the ordinary way, where the approval gate sees it. So the
script never asks for approval, and one a restart cut is simply run again. Each call goes
through a registry with the agent's own hooks, and is listed on the run card, since no other
step shows it. A script that is unsure of a tool's name or parameters looks them up
(`discovery.py`) before it calls. Calls that do not wait on one another it may ask for together
(`tools.batch`): they are made side by side, a few at a time, and are answered and listed in
the order they were written. Tools that only read need no order between them, and a hook or an
MCP call keeps nothing from one call to the next.

An agent whose file says `script_calls: gated` is handed a script that calls the tools that
change things too. Each such call is put to the approval gate before it runs (`gate.py`); the
script still asks nobody, and ends on a call a person would be asked about. What such a script
did before a restart cut it cannot be told from the log, since a call it made is kept only
with its result: it is closed as cut and never run again, whatever it had called.

A script may also ask a model itself, to sort a text among a few labels or to shorten one
(`llm_calls.py`). The server asks for it (`model_calls.py`), and each asking is one more of
the script's calls on the run card, with what it cost.

What a script keeps for a later run (`store`, `load`) is written once, when it ended well
(`store_session.py`). A script cut while it ran kept nothing, and is run again as if for the
first time; one cut after it ended and before its answer was saved is run again over what it
had kept.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts_script as t
from my_agent_crew import texts_script_llm as words
from my_agent_crew.mcp.config import CODEMODE
from my_agent_crew.mcp.tools import McpTool
from my_agent_crew.script.gate import script_gate
from my_agent_crew.script.kept import nowhere
from my_agent_crew.script.limits import (
    LLM_SUMMARY_CHARS,
    MAX_BATCH,
    MAX_CALLS,
    MAX_LLM_CALLS,
    MAX_LLM_TEXT_CHARS,
    MAX_SOURCE_CHARS,
)
from my_agent_crew.script.model_calls import Ask, ModelCalls, agents_model
from my_agent_crew.script.nested import Gate, ScriptRun
from my_agent_crew.script.runner import run_script
from my_agent_crew.script.scope import SCRIPT_TOOL, callable_tools, writes_too
from my_agent_crew.script.signature import call_line, signature
from my_agent_crew.script.store_session import Kept, turn_kept
from my_agent_crew.tools.registry import Tool, ToolError, ToolRegistry
from my_agent_crew.tools.result import ToolResult

if TYPE_CHECKING:
    from my_agent_crew.agent.loop import AgentDeps

# Lines of the description that name a tool, the agent's own and its servers' together.
MAX_LISTED = 30
PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {"script": {"type": "string", "description": t.SCRIPT_SOURCE}},
    "required": ["script"],
}


@dataclass(frozen=True)
class ScriptTool(Tool):
    """Held by an agent with a tool a script may call, whatever its own list says."""

    def to_dict(self) -> dict[str, Any]:
        # For the owner's screens: it follows what the agent may read, not its allow-list.
        return {**super().to_dict(), "with_reads": True}


def _description(
    builtins: Sequence[Tool], scripted: Sequence[McpTool], gated: bool, asks: bool = False
) -> str:
    """The agent's own tools come first, each with its parameters: what one is for is in its
    own declaration. Then the tools the owner opened for scripts, while lines are left. The
    model is only told how many more a script may call: past the last line, or never opened.
    `gated` for an agent told its scripts call the tools that change things as well, `asks`
    for one whose scripts can ask a model."""
    own = [f"- {call_line(tool)}" for tool in builtins[:MAX_LISTED]]
    opened = [tool for tool in scripted if tool.exposure == CODEMODE]
    served = [signature(tool) for tool in opened[: MAX_LISTED - len(own)]]
    left = len(builtins) + len(scripted) - len(own) - len(served)
    if left:
        (served if scripted else own).append(t.SCRIPT_MORE.format(count=left))
    told = (t.SCRIPT_DESCRIPTION_GATED if gated else t.SCRIPT_DESCRIPTION).format(
        calls=MAX_CALLS,
        batch=MAX_BATCH,
        example=t.SCRIPT_BATCH_EXAMPLE,
        builtins=t.SCRIPT_BUILTINS.format(lines="\n".join(own)) if own else "",
        mcp=t.SCRIPT_MCP.format(lines="\n".join(served)) if served else "",
    )
    if not asks:
        return told
    return told + words.LLM_DESCRIPTION.format(
        default=LLM_SUMMARY_CHARS, most=MAX_LLM_CALLS, chars=MAX_LLM_TEXT_CHARS
    )


async def run_source(
    source: str,
    held: ToolRegistry,
    gate: Gate | None = None,
    kept: Kept | None = None,
    model: Ask | None = None,
) -> tuple[ToolResult, str]:
    """Runs one script against the tools in `held`, and hands back how it ended beside what
    it printed, which the result holds only mixed with the rest. The one way a script is
    run: a turn's `tool_script` comes here, and so does the script of a schedule
    (`scheduler/script_job.py`). What it wrote with `store` is kept in `kept` once it ended
    well, and never otherwise; when even then none of it could be kept, the script failed.
    `model` answers what the script asks a model itself; without one it can ask none."""
    made = ScriptRun(held, gate, keep=kept.answer if kept is not None else nowhere)
    asked = ModelCalls(made, model)
    outcome = await run_script(source, made.answer, lookup=asked.lookup, call_many=made.answer_many)
    printed = said = outcome.output.rstrip()
    if outcome.error:
        said = f"{said}\n{outcome.error}" if said else outcome.error
    lost = kept.commit() if kept is not None and outcome.ok else None
    if lost:
        said = f"{said}\n{lost}" if said else lost
    ok = outcome.ok and not lost
    if not ok:
        said = f"{t.SCRIPT_FAILED}\n{said}".rstrip()
    result = ToolResult(
        ok=ok,
        output=said or t.SCRIPT_NO_OUTPUT,
        calls=tuple(made.calls),
        received_chars=made.received,
        printed_chars=len(printed),
    )
    return result, printed


def script_tool(
    registry: Callable[[], ToolRegistry],
    scripted: Sequence[McpTool] = (),
    gate: Gate | None = None,
    keeper: Callable[[], Kept | None] | None = None,
    model: Ask | None = None,
) -> Tool:
    """One agent's `tool_script`. `registry` hands back the agent's tools as they are when
    a script runs; `scripted` are the MCP tools it is told it may call from one. With a
    `gate`, its scripts call the tools that change things too, each put to the gate first.
    `keeper` says, as a script begins, where that one keeps what it stores; without one a
    script has nowhere. `model` is what its scripts ask when they ask a model; without one
    they are told of none.
    """
    gated = gate is not None

    async def run(arguments: dict[str, Any]) -> ToolResult:
        source = arguments.get("script")
        if not isinstance(source, str) or not source.strip():
            raise ToolError(t.SCRIPT_NO_SOURCE)
        if len(source) > MAX_SOURCE_CHARS:
            raise ToolError(t.SCRIPT_TOO_LONG.format(most=MAX_SOURCE_CHARS))
        kept = keeper() if keeper is not None else None
        return (await run_source(source, registry(), gate, kept, model))[0]

    own = [tool for tool in callable_tools(registry(), gated) if not isinstance(tool, McpTool)]
    return ScriptTool(
        name=SCRIPT_TOOL,
        description=_description(own, scripted, gated, model is not None),
        parameters=PARAMETERS,
        run=run,
        # A script that only reads makes calls that may each be made again. One that may
        # change things is not made again: nothing kept says what it had done when cut.
        replay_safe=not gated,
    )


def hand_script(deps: AgentDeps, scripted: Sequence[McpTool] = ()) -> None:
    """Hands the agent the script tool, last of what it holds now, when a script of its
    would have a tool to call: one of its own that only reads, or one of `scripted`. Or,
    for an agent whose scripts may change things, any of its own a script may call."""
    gate = script_gate(deps) if writes_too(deps.settings) else None
    if scripted or callable_tools(deps.tools, gate is not None):
        # Read when a script runs, not now: the registry is replaced on the next hand-out.
        keeper = partial(turn_kept, deps)
        model = agents_model(deps)
        deps.tools.register(script_tool(lambda: deps.tools, scripted, gate, keeper, model))
