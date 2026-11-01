"""Out of credit, the Claude route steps aside: the chain moves on to OpenRouter, and
for a while the provider does not even ask. Without a key nothing changes at all."""

import json
import time
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from my_agent_crew.config import Route, Settings
from my_agent_crew.config_secrets import secrets_from
from my_agent_crew.llm.anthropic import AnthropicProvider
from my_agent_crew.llm.anthropic_errors import OutOfCredit
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.llm.provider import ProviderChain
from my_agent_crew.llm.types import Completion, Message, RouteFailed, RouteRetry
from my_agent_crew.server.agent_assembly import build_providers, usable_routes
from my_agent_crew.server.credential_checks import run_check
from tests.conftest import collect

HI = [Message(role="user", content="hi")]
LOW = "Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing."


def _out_of_credit(seen: list, status: int = 400, kind: str = "invalid_request_error"):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = {"type": "error", "error": {"type": kind, "message": LOW}}
        return httpx.Response(status, text=json.dumps(body))

    return AnthropicProvider("k", httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize(
    ("status", "kind"), [(400, "invalid_request_error"), (402, "billing_error")]
)
async def test_a_used_up_balance_is_out_of_credit_and_not_retried(status, kind):
    seen: list = []
    with pytest.raises(OutOfCredit) as caught:
        await collect(_out_of_credit(seen, status, kind).stream(HI, [], "claude-sonnet-5-5"))
    assert caught.value.transient is False and "credit" in str(caught.value)


async def test_after_running_out_it_stops_asking_until_the_pause_is_over(monkeypatch):
    seen: list = []
    provider = _out_of_credit(seen)
    with pytest.raises(OutOfCredit):
        await collect(provider.stream(HI, [], "claude-sonnet-5-5"))
    with pytest.raises(OutOfCredit) as caught:
        await collect(provider.stream(HI, [], "claude-sonnet-5-5"))
    assert len(seen) == 1 and "min" in str(caught.value)

    clock = time.monotonic() + provider.credit_cooldown_s + 1
    monkeypatch.setattr("my_agent_crew.llm.anthropic.time.monotonic", lambda: clock)
    with pytest.raises(OutOfCredit):
        await collect(provider.stream(HI, [], "claude-sonnet-5-5"))
    assert len(seen) == 2


async def test_the_chain_falls_back_to_openrouter_when_the_credit_is_gone():
    seen: list = []
    openrouter = ScriptedProvider([completion("from openrouter")], name="openrouter")
    chain = ProviderChain(
        {"anthropic": _out_of_credit(seen), "openrouter": openrouter},
        [
            Route("anthropic", "claude-sonnet-5-5"),
            Route("openrouter", "deepseek/deepseek-v4-flash"),
        ],
    )
    items = await collect(chain.stream(HI, []))

    assert not any(isinstance(i, RouteRetry) for i in items)
    failed = next(i for i in items if isinstance(i, RouteFailed))
    assert failed.provider == "anthropic" and "credit" in failed.error
    assert isinstance(items[-1], Completion) and items[-1].provider == "openrouter"
    assert len(seen) == 1


def test_the_key_comes_from_the_environment_only():
    assert secrets_from({"ANTHROPIC_API_KEY": "sk-test"})["anthropic_api_key"] == "sk-test"
    assert secrets_from({"ANTHROPIC_API_KEY": ""})["anthropic_api_key"] is None
    assert secrets_from({})["anthropic_api_key"] is None


def test_the_provider_is_built_only_with_a_key_and_its_routes_drop_without_one(tmp_path: Path):
    routes = (Route("anthropic", "claude-sonnet-5-5"), Route("openrouter", "x/y"))
    base = Settings(home=tmp_path, routes=routes, openrouter_api_key="or")
    client = httpx.AsyncClient()

    without = build_providers(base, client, env={})
    assert "anthropic" not in without
    assert usable_routes(routes, without, routes) == [routes[1]]

    with_key = build_providers(replace(base, anthropic_api_key="k"), client, {})
    assert isinstance(with_key["anthropic"], AnthropicProvider)
    assert usable_routes(routes, with_key, routes) == list(routes)


async def test_the_key_check_lists_the_models_for_free_and_never_echoes_the_key():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        ok = request.headers.get("x-api-key") == "good-key"
        return httpx.Response(200 if ok else 401, text="invalid bad-key")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        good = await run_check("anthropic", "good-key", client)
        bad = await run_check("anthropic", "bad-key", client)
    assert good["ok"] is True and bad["ok"] is False and "401" in bad["detail"]
    assert seen[0].method == "GET" and seen[0].url.path == "/v1/models"
    assert "anthropic-version" in seen[0].headers and "bad-key" not in bad["detail"]
