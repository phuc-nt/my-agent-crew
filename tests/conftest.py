from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import pytest

from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.config import Route, Settings
from my_agent_crew.llm.fake import EchoProvider, ScriptedProvider
from my_agent_crew.llm.provider import Provider, ProviderChain, ProviderError
from my_agent_crew.llm.types import Completion
from my_agent_crew.skills import BUILTIN_DIR, load_skills
from my_agent_crew.store import Store
from my_agent_crew.tools import Tool, ToolRegistry
from my_agent_crew.tools.memory import build_memory_tools
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
    """Deps with a scripted model, real workspace/memory tools and the builtin skills."""
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    scripted = ScriptedProvider(script)
    all_providers: dict[str, Provider] = {"scripted": scripted, "fake": EchoProvider()}
    all_providers.update(providers or {})
    tools = ToolRegistry(
        [*build_workspace_tools(settings.workspace_dir), *build_memory_tools(store), *extra_tools]
    )
    return AgentDeps(
        settings=settings,
        chain=ProviderChain(all_providers, settings.routes),
        tools=tools,
        store=store,
        skills=load_skills(BUILTIN_DIR),
    )


@pytest.fixture
def deps_factory(settings: Settings, store: Store):
    def factory(script=(), extra_tools=(), providers=None, **overrides) -> AgentDeps:
        return make_deps(replace(settings, **overrides), store, script, extra_tools, providers)

    return factory


async def collect(events) -> list:
    return [event async for event in events]
