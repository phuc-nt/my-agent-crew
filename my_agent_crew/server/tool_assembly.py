"""Which tools one agent gets. An assistant gets what it always got; a work agent also
gets the editing and searching tools, and either may narrow the set with `tools` in its
profile so a reviewer cannot write code and a scout cannot run a shell."""

from __future__ import annotations

import logging
from collections.abc import Sequence

import httpx

from my_agent_crew.agents import AgentProfile
from my_agent_crew.browser.pool import BrowserPool
from my_agent_crew.config_browser import browser_root
from my_agent_crew.llm.metered_chain import MeteredChain
from my_agent_crew.llm.provider import ProviderChain
from my_agent_crew.server.browser_runtime import browser_tools_of
from my_agent_crew.server.tool_list_names import Reason, listable, listed_elsewhere
from my_agent_crew.skills import Skill
from my_agent_crew.store import Store
from my_agent_crew.tools import Tool, ToolRegistry
from my_agent_crew.tools.artifact import build_artifact_tools
from my_agent_crew.tools.artifact_files import build_artifact_file_tools
from my_agent_crew.tools.ask_user import build_ask_user_tool
from my_agent_crew.tools.conversation_search import build_conversation_search_tool
from my_agent_crew.tools.hooks import HookRunner
from my_agent_crew.tools.image import build_image_tool
from my_agent_crew.tools.memory import build_memory_tools
from my_agent_crew.tools.memory_user import build_user_memory_tools
from my_agent_crew.tools.output_read import build_output_read_tool
from my_agent_crew.tools.output_spill import READ_TOOL, Spill
from my_agent_crew.tools.output_summary import chain_summariser
from my_agent_crew.tools.pdf import build_pdf_tool
from my_agent_crew.tools.progress_note import build_progress_note_tool
from my_agent_crew.tools.schedule_create import build_schedule_create_tool
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


def allowed(
    tools: Sequence[Tool], names: Sequence[str], agent_id: str, why: Reason | None = None
) -> list[Tool]:
    """An empty allow-list means every tool. A name nobody built is a warning, not an
    error: a profile that lists a tool from a newer version should still start.

    `why` knows the tools that are not built here (`tool_list_names`). A name it explains
    is not called unknown: it is passed over when the tool is handed later, and otherwise
    the warning says why the list does not bring it."""
    if not names:
        return list(tools)
    wanted = set(names)
    kept = [tool for tool in tools if tool.name in wanted]
    for missing in sorted(wanted - {tool.name for tool in kept} - OPTIONAL_TOOLS):
        reason = why(missing) if why else None
        if reason is None:
            logger.warning("agent %s: tools lists unknown tool %s", agent_id, missing)
        elif reason:
            logger.warning("agent %s: tools lists %s, %s", agent_id, missing, reason)
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
    """The agent's tools alone, for a caller that asks nothing about its list."""
    return assemble(profile, client, store, skills, extra, vision, chain)[0]


def assemble(
    profile: AgentProfile,
    client: httpx.AsyncClient,
    store: Store,
    skills: Sequence[Skill],
    extra: Sequence[Tool] = (),
    vision: ProviderChain | None = None,
    chain: ProviderChain | None = None,
    browser: BrowserPool | None = None,
) -> tuple[ToolRegistry, tuple[str, ...]]:
    """The agent's tools, and the names a `tools:` list can bring it (`listable`).

    `vision` is the chain pictures go to; without one no agent can read images.

    `chain` is the agent's own route chain, used to summarise the middle of an over-cap
    text output. Without one the output is cut instead, which is what every caller that
    does not pass a chain gets. Every call either chain makes here lands in the usage
    ledger under what it was for.

    `browser` is where the agent's browser is started; without it no agent gets a
    browser tool."""
    pictures = MeteredChain(vision, store, profile.id, "image") if vision is not None else None
    pages = MeteredChain(vision, store, profile.id, "pdf") if vision is not None else None
    tools: list[Tool] = [
        *build_workspace_tools(profile.workspace, profile.settings.write_paths),
        *build_web_tools(profile.settings, client),
        *build_memory_tools(
            profile.memory_dir,
            profile.memory_file,
            profile.settings.user_dir,
            clock=profile.settings.now,
        ),
        *build_user_memory_tools(profile.settings.user_dir, store, profile.id),
        build_conversation_search_tool(store, profile.id, profile.is_master),
        # The vault lives beside the daily notes, so every agent that has memory has one.
        # It stays empty until something compiles into it, and an empty vault costs one
        # absent prompt section.
        *build_wiki_tools(profile.memory_dir),
        build_shell_tool(
            profile.workspace,
            network=profile.settings.shell_network,
            write_paths=profile.shell_write_dirs,
            deny_patterns=profile.settings.shell_deny_patterns,
            # What the browsers are signed in to: no sandboxed command reads it.
            private=(browser_root(profile.settings.home),),
        ),
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
        build_pdf_tool((profile.workspace, profile.settings.home), pages),
        # Proposing a schedule is gated by `ask_reason`, which always stops for a person.
        # An agent with a `tools:` allow list still needs the name listed to have it.
        build_schedule_create_tool(
            store, profile.id, tuple(skill.name for skill in skills), profile.settings.now
        ),
        # A canvas keeps every version, so no tool that writes one asks first; only
        # `artifact_export` does, which writes over a workspace file. A page and a diff are
        # sized to the same cap the registry below cuts at.
        *build_artifact_tools(
            store,
            profile.id,
            profile.is_master,
            profile.settings.tool_output_chars,
            profile.settings.zone,
        ),
        *build_artifact_file_tools(
            store,
            profile.id,
            profile.is_master,
            profile.settings.tool_output_chars,
            profile.workspace,
            profile.settings.write_paths,
        ),
    ]
    # Made for every agent and held by a work agent only: an assistant whose list names
    # one is then told the mode keeps it, rather than that nobody knows the name.
    work_only = [
        build_edit_tool(profile.workspace, profile.settings.write_paths),
        *build_search_tools(profile.workspace),
    ]
    if profile.is_work:
        tools += work_only
    if pictures is not None:
        # The crew home is a root too, so a delegate can read the master's inbox.
        tools.append(build_image_tool((profile.workspace, profile.settings.home), pictures))
    tools += list(extra)
    # Rereading is a capability like any other: listed in `tools`, or everything is allowed.
    # The spill file and the pointer to it exist only for an agent that can follow the
    # pointer, so a narrowed agent without it behaves exactly as before.
    spill = Spill(profile.settings.home)
    limit = profile.settings.tool_output_chars
    tools.append(build_output_read_tool(store, spill, limit))
    why = listed_elsewhere(profile, {tool.name for tool in work_only})
    kept = allowed(tools, profile.tools, profile.id, why)
    # The agent's `browser` key alone brings these and alone keeps them away: a list
    # written before the key was set would otherwise quietly leave the browser out.
    kept += browser_tools_of(browser, profile, limit, pictures)
    can_reread = any(tool.name == READ_TOOL for tool in kept)
    hooks = HookRunner(profile.hooks, profile.id) if profile.hooks else None
    summariser = None
    if chain is not None:
        summariser = chain_summariser(MeteredChain(chain, store, profile.id, "tool_summary"))
    registry = ToolRegistry(kept, limit, hooks, summariser, spill if can_reread else None)
    return registry, listable((tool.name for tool in tools), why)
