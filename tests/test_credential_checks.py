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
