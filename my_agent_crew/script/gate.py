"""What the approval gate says of a call a script makes to a tool that changes things.

A script waits for nobody: a turn that pauses keeps nothing in memory, so a call cannot stop
half-way through a script to ask. The gate is asked before the call runs instead, with the
rules a direct call meets (`agent/tool_gate.verdict`), and anything but "run" ends the script
with words that say what to do: make the call directly, where a person can be asked.

Those words never repeat what the call was asked to do. A command may hold a secret, and a
refusal is kept with the run.

The script a schedule runs has no conversation to go by (`scheduler/script_job.py`). It is
judged by the same rules as a job's own turn would be, one nobody watches: what would wait
for a person ends it, and nothing waits.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts_script as t
from my_agent_crew.agent.tool_gate import ASK, RUN, Allowed, ask_reason_for, verdict
from my_agent_crew.agent.turn_context import turn_conversation_id
from my_agent_crew.tools.shell import deny_reason

if TYPE_CHECKING:
    from my_agent_crew.agent.loop import AgentDeps
    from my_agent_crew.script.nested import Gate


@dataclass(frozen=True)
class Unattended:
    """What a schedule's script goes by where a turn has its conversation: nobody is there
    to authorise a tool, as in the conversation a job opens, and nobody ever said of one to
    always allow it."""

    autonomous: bool = True
    auto_approve: tuple[str, ...] = ()


def _asked(deps: AgentDeps, name: str, arguments: dict[str, Any]) -> str:
    """Why the gate would ask. A pattern of the agent's ask list is the owner's own words
    and is named; a tool's own reason may quote the call, so it is not passed on."""
    tool = deps.tools.get(name)
    own = tool is not None and tool.ask_reason is not None
    pattern = None if own else ask_reason_for(deps, name, arguments)
    if pattern:
        return t.SCRIPT_GATE_ASK_LIST.format(name=name, pattern=pattern)
    return t.SCRIPT_GATE_ASKS.format(name=name)


def _refusal(deps: AgentDeps, allowed: Allowed, name: str, arguments: dict[str, Any]) -> str | None:
    """None for a call the gate lets run, else the words the script ends on."""
    said = verdict(deps, allowed, name, arguments)
    if said == RUN:
        return None
    if said == ASK:
        return _asked(deps, name, arguments)
    pattern = deny_reason(arguments, deps.settings.shell_deny_patterns)
    return t.SCRIPT_GATE_DENIED.format(name=name, pattern=pattern)


def script_gate(deps: AgentDeps) -> Gate:
    """The gate for one agent's scripts. The conversation is the turn's own, read as each
    call is asked for: what its person allows is theirs to change at any time."""

    def refusal(name: str, arguments: dict[str, Any]) -> str | None:
        conv_id = turn_conversation_id()
        try:
            conv = deps.store.get(conv_id) if conv_id else None
        except KeyError:
            conv = None
        if conv is None:
            # Nobody's rules to go by: a call that changes things is not made on a guess.
            return t.SCRIPT_GATE_NO_TURN.format(name=name)
        return _refusal(deps, conv, name, arguments)

    return refusal


def job_gate(deps: AgentDeps) -> Gate:
    """The gate for the script a schedule of this agent runs."""
    return partial(_refusal, deps, Unattended())
