"""Which tools one agent gets. An assistant gets what it always got; a work agent also
gets the editing and searching tools, and either may narrow the set with `tools` in its
profile so a reviewer cannot write code and a scout cannot run a shell."""

from __future__ import annotations

import logging
from collections.abc import Sequence

import httpx

from my_agent_crew.agents import AgentProfile
from my_agent_crew.llm.provider import ProviderChain
from my_agent_crew.skills import Skill
from my_agent_crew.store import Store
from my_agent_crew.tools import Tool, ToolRegistry
from my_agent_crew.tools.ask_user import build_ask_user_tool
from my_agent_crew.tools.hooks import HookRunner
from my_agent_crew.tools.image import build_image_tool
from my_agent_crew.tools.memory import build_memory_tools
from my_agent_crew.tools.memory_user import build_user_memory_tools
from my_agent_crew.tools.output_summary import chain_summariser
from my_agent_crew.tools.pdf import build_pdf_tool
from my_agent_crew.tools.progress_note import build_progress_note_tool
from my_agent_crew.tools.shell import build_shell_tool
from my_agent_crew.tools.skills import build_skill_tools
from my_agent_crew.tools.web import build_web_tools
from my_agent_crew.tools.wiki import build_wiki_tools
from my_agent_crew.tools.workspace import build_workspace_tools
from my_agent_crew.tools.workspace_edit import build_edit_tool
from my_agent_crew.tools.workspace_search import build_search_tools

logger = logging.getLogger(__name__)


# Real tools that are only built when their backing service is configured. Listing one
# is a choice about the agent's role, not a mistake, so a bare machine stays quiet about
# it. `web_search` is not here: it always builds, because DuckDuckGo needs no key.
OPTIONAL_TOOLS = frozenset({"image_read"})


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
    vision: ProviderChain | None = None,
    chain: ProviderChain | None = None,
) -> ToolRegistry:
    """`vision` is the chain pictures go to; without one no agent can read images.

    `chain` is the agent's own route chain, used to summarise the middle of an over-cap
    text output. Without one the output is cut instead, which is what every caller that
    does not pass a chain gets."""
    tools: list[Tool] = [
        *build_workspace_tools(profile.workspace),
        *build_web_tools(profile.settings, client),
        *build_memory_tools(
            profile.memory_dir,
            profile.memory_file,
            profile.settings.user_dir,
            clock=profile.settings.now,
        ),
        *build_user_memory_tools(profile.settings.user_dir, store, profile.id),
        # The vault lives beside the daily notes, so every agent that has memory has one.
        # It stays empty until something compiles into it, and an empty vault costs one
        # absent prompt section.
        *build_wiki_tools(profile.memory_dir),
        build_shell_tool(profile.workspace),
        *build_skill_tools(skills),
        # Asking is not a capability an agent should have to be granted: an agent that may
        # act but may not ask would guess instead, which is worse. It stays out of
        # OPTIONAL_TOOLS so a profile that narrows `tools` and forgets it gets a warning.
        build_ask_user_tool(),
        # Same reasoning as asking, one step milder: telling someone what you are doing is
        # not a privilege either, and a run that goes quiet for ten minutes looks stuck
        # whether or not it is.
        build_progress_note_tool(),
        # Registered whether or not there is a vision chain: a typeset PDF reads fine
        # without one, and only a scanned page needs to say it could not.
        build_pdf_tool((profile.workspace, profile.settings.home), vision),
    ]
    if profile.is_work:
        tools += [build_edit_tool(profile.workspace), *build_search_tools(profile.workspace)]
    if vision is not None:
        # The crew home is a root too, so a delegate can read the master's inbox.
        tools.append(build_image_tool((profile.workspace, profile.settings.home), vision))
    tools += list(extra)
    kept = allowed(tools, profile.tools, profile.id)
    hooks = HookRunner(profile.hooks, profile.id) if profile.hooks else None
    summariser = chain_summariser(chain) if chain is not None else None
    return ToolRegistry(kept, profile.settings.tool_output_chars, hooks, summariser)
