"""A task handed to another agent from a script: `tools.delegate`.

By its own declaration the tool only reads: it may be made again after a restart, and it
asks nobody. It is no read all the same. It sets another agent to work for minutes, on the
conversation's money, so a script calls it by a rule of its own and never by
`scope.only_reads`: the agent's scripts are the ones that change things (`script_calls:
gated`), the agent holds `delegate`, and the script runs in a turn of the agent's own. A
task the agent was itself handed is no such turn, and a schedule's script has no
conversation the task's would be the child of. Anywhere else the script is told what it is
told of every tool kept from scripts: to call it directly.

The approval gate is not asked about it, as it is not when the model calls `delegate`
itself: what the other agent then does is put to the gate in that agent's own conversation.

Each such call goes by an id of its own (`own_call`). The conversation one opens is found
again by the call that opened it, and every call of a script would otherwise go by the one
id, the script's.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from typing import Any

from my_agent_crew import texts_script_delegate as words
from my_agent_crew.agent.turn_context import (
    calling_as,
    tool_call_id,
    turn_conversation_id,
    turn_depth,
)
from my_agent_crew.agents.roster import DELEGATE_TOOL_NAME
from my_agent_crew.script import limits
from my_agent_crew.store.conversation_lookup import nested_call_id
from my_agent_crew.tools.registry import Tool, ToolRegistry


def hands_on(held: ToolRegistry, gated: bool) -> bool:
    """Whether the agent's scripts hand tasks on at all, wherever one of them runs: what
    the model is told of `tool_script` goes by this."""
    return gated and held.get(DELEGATE_TOOL_NAME) is not None


def may_delegate(held: ToolRegistry, gated: bool) -> bool:
    """Whether the script beginning now may hand a task on: the agent's scripts do, and
    this one runs in a turn of the agent's own, with a conversation to be the parent."""
    return hands_on(held, gated) and turn_depth() == 0 and bool(turn_conversation_id())


def off_target(tool: Tool, arguments: dict[str, Any]) -> str | None:
    """Why a task may not go to the agent the script names, known before any call is made;
    None for a task that may, and for a call of any other tool. The agents it may go to are
    the ones the tool itself was built with, and no agent named is the agent itself."""
    if tool.name != DELEGATE_TOOL_NAME:
        return None
    allowed = tool.parameters.get("properties", {}).get("agent", {}).get("enum")
    target = arguments.get("agent")
    if not isinstance(allowed, list) or not target or str(target) in allowed:
        return None
    told = ", ".join(str(agent) for agent in allowed)
    return words.DELEGATE_WRONG_AGENT.format(name=tool.name, allowed=told)


@contextmanager
def own_call(tool: Tool, number: int) -> Iterator[None]:
    """A task handed on is carried out under an id of its own: the script's, then the
    number of the call in it. The same script run again under the same id finds the
    conversation each of its tasks opened, and opens none. Any other call, and a script
    with no id to go by, goes by what is there."""
    script_id = tool_call_id()
    if tool.name != DELEGATE_TOOL_NAME or not script_id:
        yield
        return
    with calling_as(nested_call_id(script_id, number)):
        yield


def handing_room() -> asyncio.Semaphore:
    """What the tasks of one batch wait on: so many are handed on at the same moment."""
    return asyncio.Semaphore(limits.MAX_PARALLEL_DELEGATE)


@asynccontextmanager
async def in_turn(tool: Tool, room: asyncio.Semaphore) -> AsyncIterator[None]:
    """Holds a task back until there is room among the ones being handed on. A call of any
    other tool waits for nothing here."""
    if tool.name != DELEGATE_TOOL_NAME:
        yield
        return
    async with room:
        yield
