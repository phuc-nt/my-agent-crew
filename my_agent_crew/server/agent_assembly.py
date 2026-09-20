"""Building one agent's `AgentDeps` out of its profile: which providers it can reach,
which routes survive the keys that are actually present, and the tools and skills it
gets. The runtime owns the shared pieces (store, hub, scheduler); this owns the per-agent
assembly so both stay readable."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import replace

import httpx

from my_agent_crew import texts
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents import AgentProfile
from my_agent_crew.agents.context import ensure_agent_dirs
from my_agent_crew.config import Route, Settings
from my_agent_crew.llm.fake import EchoProvider
from my_agent_crew.llm.openrouter import OpenRouterProvider
from my_agent_crew.llm.provider import Provider, ProviderChain
from my_agent_crew.skills import BUILTIN_DIR, Skill, load_skills
from my_agent_crew.store import Store
from my_agent_crew.tools import ToolRegistry
from my_agent_crew.tools.memory import build_memory_tools
from my_agent_crew.tools.memory_user import build_user_memory_tools
from my_agent_crew.tools.shell import build_shell_tool
from my_agent_crew.tools.skills import build_skill_tools
from my_agent_crew.tools.web import build_web_tools
from my_agent_crew.tools.workspace import build_workspace_tools

logger = logging.getLogger(__name__)


def build_providers(settings: Settings, client: httpx.AsyncClient) -> dict[str, Provider]:
    providers: dict[str, Provider] = {"fake": EchoProvider()}
    if settings.openrouter_api_key:
        providers["openrouter"] = OpenRouterProvider(settings.openrouter_api_key, client)
    return providers


def usable_routes(
    routes: Sequence[Route], providers: dict[str, Provider], fallback: Sequence[Route]
) -> list[Route]:
    """Routes whose provider is actually built. A profile written for OpenRouter must
    still load when the key is absent (echo runs, tests), so such routes are dropped and
    the global routes take over; only when nothing usable remains is it an error."""
    kept = [r for r in routes if r.provider in providers]
    if kept:
        return kept
    kept = [r for r in fallback if r.provider in providers]
    if kept:
        logger.warning("no usable route among %s; using %s", list(routes), kept)
        return kept
    raise ValueError(texts.NO_USABLE_ROUTE.format(routes=list(routes)))


def warn_unknown_schedule_skills(profile: AgentProfile, skills: Sequence[Skill]) -> None:
    """A schedule naming a skill that no longer loads would silently run without it."""
    known = {skill.name for skill in skills}
    for schedule in profile.schedules:
        for name in schedule.skills:
            if name not in known:
                logger.warning(
                    "agent %s: schedule %s names unknown skill %s", profile.id, schedule.id, name
                )


def build_agent_deps(
    profile: AgentProfile,
    providers: dict[str, Provider],
    client: httpx.AsyncClient,
    store: Store,
    fallback_routes: Sequence[Route] = (),
) -> AgentDeps:
    ensure_agent_dirs(profile)
    routes = usable_routes(profile.settings.routes, providers, fallback_routes)
    if routes != list(profile.settings.routes):
        profile = replace(profile, settings=replace(profile.settings, routes=tuple(routes)))
    skills = load_skills(BUILTIN_DIR, *profile.skills_dirs)
    warn_unknown_schedule_skills(profile, skills)
    tools = ToolRegistry(
        [
            *build_workspace_tools(profile.workspace),
            *build_web_tools(profile.settings, client),
            *build_memory_tools(profile.memory_dir, profile.memory_file, profile.settings.user_dir),
            *build_user_memory_tools(profile.settings.user_dir, store, profile.id),
            build_shell_tool(profile.workspace),
            *build_skill_tools(skills),
        ]
    )
    chain = ProviderChain(providers, profile.settings.routes)
    return AgentDeps(
        settings=profile.settings,
        chain=chain,
        tools=tools,
        store=store,
        skills=skills,
        profile=profile,
    )
