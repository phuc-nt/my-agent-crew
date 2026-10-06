"""What an agent is handed of the MCP servers its profile names.

Every tool of those servers but the hidden ones. Ahead of them come `tool_search`, when
some are not told up front, and `tool_script`, when some may be called from a script.
Handing out starts by taking back what was handed before, so it can be done whenever a
server or a profile changes: an agent is always left with what the servers hold now, each
tool once and in the same place.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING

from my_agent_crew.mcp.config import HIDDEN
from my_agent_crew.mcp.tool_search import SEARCH_TOOL, search_tool
from my_agent_crew.mcp.tools import PREFIX, McpTool, held_back
from my_agent_crew.script.tool import SCRIPT_TOOL, script_tool, scriptable

if TYPE_CHECKING:
    from my_agent_crew.agent.loop import AgentDeps
    from my_agent_crew.mcp.hub import Link

logger = logging.getLogger(__name__)


def hand_out(deps: AgentDeps, links: Mapping[str, Link]) -> None:
    companions = (SEARCH_TOOL, SCRIPT_TOOL)
    back = [n for n in deps.tools.names() if n.startswith(PREFIX) or n in companions]
    if back:
        # In one build of the toolbox, however many there are to take back.
        deps.tools = deps.tools.without(*back)
    handed: dict[str, McpTool] = {}
    for server in deps.agent.mcp:
        link = links.get(server)
        if link is None:
            logger.warning("agent %s: no MCP server named %s", deps.agent.id, server)
            continue
        for tool in link.tools:
            if tool.exposure != HIDDEN:
                # Two servers can come to one name; the server named first keeps it.
                handed.setdefault(tool.name, tool)
    waiting = [tool for tool in handed.values() if held_back(tool)]
    if waiting:
        # Before the tools themselves: the built-ins and it are what never moves.
        about = {tool.server: links[tool.server].server.description for tool in waiting}
        deps.tools.register(search_tool(waiting, about))
    scripted = [tool for tool in handed.values() if scriptable(tool)]
    if scripted:
        # Read when a script runs, not now: the registry is replaced on the next hand-out.
        deps.tools.register(script_tool(lambda: deps.tools, scripted))
    for tool in handed.values():
        deps.tools.register(tool)
