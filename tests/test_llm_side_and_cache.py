"""The two spending levers outside the routes: how long Claude keeps the stable part of the
prompt cached, and which routes write a conversation's title and summary."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import httpx
import pytest

from my_agent_crew.config_llm import LlmSettings, llm_settings
from my_agent_crew.config_parse import Route
from my_agent_crew.llm.anthropic_wire import CACHE, request_body
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.llm.provider import ProviderChain
from my_agent_crew.llm.types import Message, ToolSpec
from my_agent_crew.memory.conversation_title import title_on_first_message
from my_agent_crew.server.agent_assembly import build_providers, side_chain

TOOL = ToolSpec("workspace_list", "List files", {"type": "object", "properties": {}})
HOUR = {"type": "ephemeral", "ttl": "1h"}


def test_the_defaults_keep_five_minutes_and_no_side_routes():
    assert llm_settings({}, {}) == LlmSettings("5m", ())


def test_env_outranks_yaml_and_an_empty_env_turns_side_routes_off():
    yaml = {"anthropic_cache_ttl": "1h", "side_routes": ["anthropic:claude-haiku-5-5"]}
    assert llm_settings({}, yaml) == LlmSettings("1h", (Route("anthropic", "claude-haiku-5-5"),))
    env = {"MY_AGENT_ANTHROPIC_CACHE_TTL": "5m", "MY_AGENT_SIDE_ROUTES": ""}
    assert llm_settings(env, yaml) == LlmSettings("5m", ())


def test_an_unknown_cache_lifetime_is_refused():
    with pytest.raises(ValueError, match="anthropic_cache_ttl"):
        llm_settings({}, {"anthropic_cache_ttl": "2h"})


def test_an_hour_marks_the_tools_and_system_but_not_the_moving_tail():
    body = request_body(
        [Message(role="system", content="s"), Message(role="user", content="u")],
        [TOOL],
        "claude-sonnet-5-5",
        "",
        100,
        "1h",
    )
    assert body["tools"][-1]["cache_control"] == HOUR
    assert body["system"][-1]["cache_control"] == HOUR
    assert body["messages"][-1]["content"][-1]["cache_control"] == CACHE


def test_the_provider_is_built_with_the_configured_lifetime(settings):
    keyed = replace(settings, anthropic_api_key="k", llm=LlmSettings(anthropic_cache_ttl="1h"))
    provider = build_providers(keyed, httpx.AsyncClient())["anthropic"]
    assert provider._cache_ttl == "1h"


def test_side_routes_without_a_built_provider_leave_the_agents_chain(settings):
    providers = {r.provider: ScriptedProvider([]) for r in settings.routes}
    providers["fake"] = ScriptedProvider([])
    unbuilt = replace(settings, llm=LlmSettings(side_routes=(Route("anthropic", "h"),)))
    assert side_chain(unbuilt, providers) is None

    built = replace(settings, llm=LlmSettings(side_routes=(Route("fake", "cheap"),)))
    chain = side_chain(built, providers)
    assert chain.routes[0] == Route("fake", "cheap")
    assert tuple(chain.routes[1:]) == tuple(settings.routes)


async def test_the_title_is_written_by_the_side_chain_when_there_is_one(deps_factory):
    deps = deps_factory(script=[completion("Tiêu đề của model chính")])
    side = ScriptedProvider([completion("Tiêu đề rẻ")])
    deps.side = ProviderChain({"side": side}, [Route("side", "cheap")])
    conv = deps.store.create()
    kept: list[asyncio.Task[None]] = []

    title_on_first_message(kept.append, deps, conv.id, "Giúp tôi ôn thi")
    await asyncio.gather(*kept, return_exceptions=True)

    assert deps.store.get(conv.id).title == "Tiêu đề rẻ"
    assert len(side.requests) == 1
