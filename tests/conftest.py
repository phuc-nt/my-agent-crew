from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents import default_profile
from my_agent_crew.agents.context import ensure_agent_dirs
from my_agent_crew.config import Route, Settings
from my_agent_crew.llm.fake import EchoProvider, ScriptedProvider
from my_agent_crew.llm.provider import Provider, ProviderChain, ProviderError
from my_agent_crew.llm.types import Completion
from my_agent_crew.skills import BUILTIN_DIR, load_skills
from my_agent_crew.store import Store
from my_agent_crew.tools import Tool, ToolRegistry
from my_agent_crew.tools.memory import build_memory_tools
from my_agent_crew.tools.shell import build_shell_tool
from my_agent_crew.tools.workspace import build_workspace_tools


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(home=tmp_path / "home", routes=(Route("scripted", "m"),), cost_cap_usd=0.5)


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


def make_deps(
    settings: Settings,
    store: Store,
    script: Sequence[Completion | ProviderError] = (),
    extra_tools: Sequence[Tool] = (),
    providers: dict[str, Provider] | None = None,
) -> AgentDeps:
    """Deps for the default agent: scripted model, real workspace/memory/shell tools and
    the builtin skills."""
    profile = default_profile(settings)
    ensure_agent_dirs(profile)
    scripted = ScriptedProvider(script)
    all_providers: dict[str, Provider] = {"scripted": scripted, "fake": EchoProvider()}
    all_providers.update(providers or {})
    tools = ToolRegistry(
        [
            *build_workspace_tools(profile.workspace),
            *build_memory_tools(profile.memory_dir, profile.memory_file, profile.settings.user_dir),
            build_shell_tool(profile.workspace),
            *extra_tools,
        ]
    )
    return AgentDeps(
        settings=settings,
        chain=ProviderChain(all_providers, settings.routes),
        tools=tools,
        store=store,
        skills=load_skills(BUILTIN_DIR),
        profile=profile,
    )


@pytest.fixture
def deps_factory(settings: Settings, store: Store):
    def factory(script=(), extra_tools=(), providers=None, **overrides) -> AgentDeps:
        return make_deps(replace(settings, **overrides), store, script, extra_tools, providers)

    return factory


async def collect(events) -> list:
    return [event async for event in events]
