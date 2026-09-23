"""A check reports on what answered, whatever shape the answer takes, and never lets the
secret it checked reach a log or the reply."""

import logging

import httpx

from my_agent_crew.channels.telegram_api import hide_token
from my_agent_crew.server.credential_checks import run_check


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_a_reply_that_is_not_an_object_is_reported_not_raised() -> None:
    async with _client(lambda request: httpx.Response(200, json=[1, 2])) as client:
        models = await run_check("ollama", "http://127.0.0.1:11434/v1", client)
        bot = await run_check("telegram", "123:abc", client)
    assert models["ok"] is True and "0" in models["detail"]
    assert bot["ok"] is True


async def test_a_tavily_key_is_checked_on_its_usage_without_spending_a_search() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers["Authorization"]))
        return httpx.Response(200, json={"key": {"usage": 12, "limit": 1000}})

    async with _client(handler) as client:
        result = await run_check("tavily", "tvly-secret", client)
    assert result == {"ok": True, "detail": "Hoạt động — đã dùng 12/1000 lượt"}
    assert seen == [("/usage", "Bearer tvly-secret")]


async def test_a_brave_key_is_checked_with_one_single_result_search() -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.params["count"], request.headers["X-Subscription-Token"]))
        return httpx.Response(200, json={"web": {"results": []}})

    async with _client(handler) as client:
        result = await run_check("brave", "brave-secret", client)
    assert result["ok"] is True
    assert seen == [("1", "brave-secret")]


async def test_a_search_key_refused_is_named_so_and_never_echoed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # A service that repeats the key it refused must not get it onto the page.
        return httpx.Response(422, text="bad token brave-secret")

    async with _client(handler) as client:
        brave = await run_check("brave", "brave-secret", client)
        tavily = await run_check("tavily", "brave-secret", client)
    assert brave["ok"] is False and "khoá sai" in brave["detail"]
    assert tavily["ok"] is False and "422" in tavily["detail"]
    assert "brave-secret" not in brave["detail"] + tavily["detail"]


async def test_a_search_key_out_of_quota_is_told_apart_from_a_wrong_one() -> None:
    async with _client(lambda request: httpx.Response(429)) as client:
        result = await run_check("tavily", "tvly-secret", client)
    assert result["ok"] is False and "429" in result["detail"]
    assert "khoá sai" not in result["detail"]


async def test_a_reply_that_is_not_json_is_a_failed_check() -> None:
    async with _client(lambda request: httpx.Response(200, text="<html>")) as client:
        result = await run_check("ollama", "http://127.0.0.1:11434/v1", client)
    assert result["ok"] is False


async def test_a_malformed_host_is_a_failed_check() -> None:
    async with httpx.AsyncClient() as client:
        result = await run_check("firecrawl", "http://[", client)
    assert result["ok"] is False


async def test_a_checked_bot_token_is_kept_out_of_the_request_log(caplog) -> None:
    token = "999:check-only-token"
    ok = {"ok": True, "result": {"username": "crew_bot"}}
    with caplog.at_level(logging.INFO, logger="httpx"):
        async with _client(lambda request: httpx.Response(200, json=ok)) as client:
            result = await run_check("telegram", token, client)
            logging.getLogger("httpx").info("HTTP Request: GET %s", f"https://x/bot{token}/getMe")
    assert result["ok"] is True and "crew_bot" in result["detail"]
    assert token not in caplog.text


def test_every_token_used_stays_hidden_with_one_filter(caplog) -> None:
    hide_token("111:first")
    hide_token("222:second")
    logger = logging.getLogger("httpx")
    with caplog.at_level(logging.INFO, logger="httpx"):
        logger.info("GET /bot111:first/x and /bot%s/y", "222:second")
    assert "111:first" not in caplog.text and "222:second" not in caplog.text
    assert len(logger.filters) == 1
