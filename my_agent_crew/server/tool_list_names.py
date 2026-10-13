"""What to say of a name in an agent's `tools:` list that no tool built with it carries.

The list chooses among the tools assembly builds. A name it cannot match there may still
be a real tool: `delegate` is handed once every agent exists, and the list is what keeps
it; the script tool, `tool_search`, a server's tools, the browser tools and the desktop
tools come by what the agent holds, the servers it names and its `browser` and `computer`
keys, whatever the list says; some tools come with the work mode. Only a name none of this
explains is one nobody knows, and that keeps the wording it always had.

Whoever edits a list is told the names it can bring by the same judge (`listable`), so a
name is offered there exactly when a list that holds it is told nothing here.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable

from my_agent_crew.agents import AgentProfile
from my_agent_crew.agents.roster import DELEGATE_TOOL_NAME
from my_agent_crew.browser.kit import BROWSER_TOOLS
from my_agent_crew.desktop.kit import DESKTOP_TOOLS
from my_agent_crew.mcp.tool_search import SEARCH_TOOL
from my_agent_crew.mcp.tools import PREFIX
from my_agent_crew.script.scope import SCRIPT_TOOL

# The name is honoured later, by whoever hands the tool: there is nothing to say.
HONOURED = ""
# The tools handed once assembly is over, which a list may still keep or leave out.
HANDED_LATER = (DELEGATE_TOOL_NAME,)
NOBODY_TO_HAND_TO = (
    "which this agent is not given: it hands work to nobody "
    "(the master, a work agent and an agent that names `delegates` do)"
)
NOT_THE_LISTS = "which the list does not decide: "
SCRIPT = NOT_THE_LISTS + (
    "an agent holds it when it holds a tool a script may call, unless `script_calls` is `none`"
)
SEARCH = NOT_THE_LISTS + "it comes with the servers named under `mcp`"
SERVER_TOOL = NOT_THE_LISTS + "a server's tools come with the servers named under `mcp`"
BROWSER = NOT_THE_LISTS + "the browser tools come with the agent's `browser` key"
DESKTOP = NOT_THE_LISTS + "the desktop tools come with the agent's `computer` key"
WORK_ONLY = "which only an agent with `mode: work` holds"


Reason = Callable[[str], str | None]


def listed_elsewhere(profile: AgentProfile, work_only: Collection[str]) -> Reason:
    """Why a name the list holds is not among the tools built with the agent: nothing to
    say when it is honoured later, the reason when the list cannot bring it, and `None`
    for a name no tool carries. `work_only` names the tools the work mode brings."""
    fixed = {
        SCRIPT_TOOL: SCRIPT,
        SEARCH_TOOL: SEARCH,
        **dict.fromkeys(BROWSER_TOOLS, BROWSER),
        **dict.fromkeys(DESKTOP_TOOLS, DESKTOP),
        **dict.fromkeys(work_only, WORK_ONLY),
    }

    def why(name: str) -> str | None:
        if name == DELEGATE_TOOL_NAME:
            return HONOURED if profile.hands_work_out else NOBODY_TO_HAND_TO
        if name.startswith(PREFIX):
            return SERVER_TOOL
        return fixed.get(name)

    return why


def listable(built: Iterable[str], why: Reason) -> tuple[str, ...]:
    """The names a `tools:` list can bring the agent, in order: the tools built with it,
    which the list chooses among, and a tool handed later that the list is honoured for.
    Asked of `why`, as the warning is, so the two never tell a name differently."""
    later = (name for name in HANDED_LATER if why(name) == HONOURED)
    return tuple(sorted({*built, *later}))
