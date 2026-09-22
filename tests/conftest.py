from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents import default_profile
from my_agent_crew.agents.context import ensure_agent_dirs
from my_agent_crew.channels import TelegramApi, TelegramChannel
from my_agent_crew.config import Route, Settings
from my_agent_crew.llm.fake import EchoProvider, ScriptedProvider
from my_agent_crew.llm.provider import Provider, ProviderChain, ProviderError
from my_agent_crew.llm.types import Completion
from my_agent_crew.skills import BUILTIN_DIR, load_skills
from my_agent_crew.store import Store
from my_agent_crew.tools import Tool, ToolRegistry
from my_agent_crew.tools.ask_user import build_ask_user_tool
from my_agent_crew.tools.memory import build_memory_tools
from my_agent_crew.tools.shell import build_shell_tool
from my_agent_crew.tools.skills import build_skill_tools
from my_agent_crew.tools.workspace import build_workspace_tools
from tests.telegram_fake import CHAT, TOKEN, FakeTelegram


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
    skills = load_skills(BUILTIN_DIR, *profile.skills_dirs)
    tools = ToolRegistry(
        [
            *build_workspace_tools(profile.workspace),
            *build_memory_tools(profile.memory_dir, profile.memory_file, profile.settings.user_dir),
            build_shell_tool(profile.workspace),
            *build_skill_tools(skills),
            build_ask_user_tool(),
            *extra_tools,
        ]
    )
    return AgentDeps(
        settings=settings,
        chain=ProviderChain(all_providers, settings.routes),
        tools=tools,
        store=store,
        skills=skills,
        profile=profile,
    )


@pytest.fixture
def deps_factory(settings: Settings, store: Store):
    def factory(script=(), extra_tools=(), providers=None, **overrides) -> AgentDeps:
        return make_deps(replace(settings, **overrides), store, script, extra_tools, providers)

    return factory


async def collect(events) -> list:
    return [event async for event in events]


# The Telegram fake lives here rather than in a test module so every test that drives the
# channel gets it by name, without one test file importing another's fixtures.
@pytest.fixture
def fake() -> FakeTelegram:
    return FakeTelegram()


@pytest.fixture
def make_channel(deps_factory, fake, tmp_path: Path):
    def factory(deps=None, clock=datetime.now) -> TelegramChannel:
        deps = deps or deps_factory(routes=(Route("fake", "echo"),))
        client = httpx.AsyncClient(transport=httpx.MockTransport(fake.handler))
        api = TelegramApi(TOKEN, client)
        hub = ActivityHub(deps.store)
        agents = {deps.agent.id: deps}
        offset = tmp_path / "telegram.offset"
        return TelegramChannel(agents, deps.agent.id, hub, api, CHAT, offset, clock=clock)

    return factory
