"""Which tools one agent gets. An assistant gets what it always got; a work agent also
gets the editing and searching tools, and either may narrow the set with `tools` in its
profile so a reviewer cannot write code and a scout cannot run a shell."""

from __future__ import annotations

import logging
from collections.abc import Sequence

import httpx

from my_agent_crew.agents import AgentProfile
from my_agent_crew.skills import Skill
from my_agent_crew.store import Store
from my_agent_crew.tools import Tool, ToolRegistry
from my_agent_crew.tools.memory import build_memory_tools
from my_agent_crew.tools.memory_user import build_user_memory_tools
from my_agent_crew.tools.shell import build_shell_tool
from my_agent_crew.tools.skills import build_skill_tools
from my_agent_crew.tools.web import build_web_tools
from my_agent_crew.tools.workspace import build_workspace_tools
from my_agent_crew.tools.workspace_edit import build_edit_tool
from my_agent_crew.tools.workspace_search import build_search_tools

logger = logging.getLogger(__name__)


# Real tools that are only built when their key is configured. Listing one is a choice
# about the agent's role, not a mistake, so an unkeyed machine stays quiet about it.
OPTIONAL_TOOLS = frozenset({"web_search"})


def allowed(tools: Sequence[Tool], names: Sequence[str], agent_id: str) -> list[Tool]:
    """An empty allow-list means every tool. A name nobody built is a warning, not an
    error: a profile that lists a tool from a newer version should still start."""
    if not names:
        return list(tools)
    wanted = set(names)
    kept = [tool for tool in tools if tool.name in wanted]
    for missing in sorted(wanted - {tool.name for tool in kept} - OPTIONAL_TOOLS):
        logger.warning("agent %s: tools lists unknown tool %s", agent_id, missing)
    return kept


def build_tools(
    profile: AgentProfile,
    client: httpx.AsyncClient,
    store: Store,
    skills: Sequence[Skill],
    extra: Sequence[Tool] = (),
) -> ToolRegistry:
    tools: list[Tool] = [
        *build_workspace_tools(profile.workspace),
        *build_web_tools(profile.settings, client),
        *build_memory_tools(profile.memory_dir, profile.memory_file, profile.settings.user_dir),
        *build_user_memory_tools(profile.settings.user_dir, store, profile.id),
        build_shell_tool(profile.workspace),
        *build_skill_tools(skills),
    ]
    if profile.is_work:
        tools += [build_edit_tool(profile.workspace), *build_search_tools(profile.workspace)]
    tools += list(extra)
    kept = allowed(tools, profile.tools, profile.id)
    return ToolRegistry(kept, profile.settings.tool_output_chars)
