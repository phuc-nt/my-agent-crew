"""One free request per kind of connection, to tell a working key from a wrong one.

Each check picks an endpoint that costs nothing and changes nothing: OpenRouter's key
info, Telegram's `getMe`, ollama's model list, a GET on the firecrawl host. Search keys
(Brave, Tavily) have no such endpoint — every call there spends quota — so they have no
check. Whatever comes back has the value cut out before it is shown, because an httpx error
names the URL it failed on and a Telegram URL carries the token; the same token is kept
out of httpx's own request log.
"""

from __future__ import annotations

from typing import Any

import httpx

from my_agent_crew import texts_credentials as t
from my_agent_crew.channels.telegram_api import hide_token
from my_agent_crew.llm.ollama import base_url as ollama_base_url

CHECK_TIMEOUT_SECONDS = 10.0
OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
TELEGRAM_API = "https://api.telegram.org"
REJECTED_STATUSES = (401, 403, 404)
# Checks whose value is a secret, so nothing said about them may contain it.
SECRET_KINDS = ("openrouter", "telegram")


def _result(ok: bool, detail: str) -> dict[str, Any]:
    return {"ok": ok, "detail": detail}


def _field(response: httpx.Response, key: str) -> Any:
    """`key` of a JSON object reply; None for any other shape, which a host that is not
    what the name says can well send."""
    body = response.json()
    return body.get(key) if isinstance(body, dict) else None


def _failed(response: httpx.Response) -> dict[str, Any]:
    if response.status_code in REJECTED_STATUSES:
        return _result(False, t.CHECK_REJECTED.format(status=response.status_code))
    return _result(False, t.CHECK_HTTP.format(status=response.status_code))


async def _openrouter(client: httpx.AsyncClient, key: str) -> dict[str, Any]:
    response = await client.get(
        OPENROUTER_KEY_URL,
        headers={"Authorization": f"Bearer {key}"},
        timeout=CHECK_TIMEOUT_SECONDS,
    )
    return _result(True, t.CHECK_OK) if response.is_success else _failed(response)


async def _telegram(client: httpx.AsyncClient, token: str) -> dict[str, Any]:
    hide_token(token)  # httpx logs the URL, and the token is in it
    response = await client.get(f"{TELEGRAM_API}/bot{token}/getMe", timeout=CHECK_TIMEOUT_SECONDS)
    if not response.is_success:
        return _failed(response)
    result = _field(response, "result")
    username = (result.get("username") if isinstance(result, dict) else None) or "?"
    return _result(True, t.CHECK_BOT.format(username=username))


async def _ollama(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    response = await client.get(f"{url.rstrip('/')}/models", timeout=CHECK_TIMEOUT_SECONDS)
    if not response.is_success:
        return _failed(response)
    models = _field(response, "data")
    models = models if isinstance(models, list) else []
    return _result(True, t.CHECK_MODELS.format(count=len(models)))


async def _reachable(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    # A self-hosted firecrawl answers its root with anything from 200 to 404; getting an
    # HTTP answer at all is what separates "running" from "wrong host".
    response = await client.get(url, timeout=CHECK_TIMEOUT_SECONDS)
    return _result(True, t.CHECK_REACHABLE.format(status=response.status_code))


CHECKS = {
    "openrouter": _openrouter,
    "telegram": _telegram,
    "ollama": _ollama,
    "firecrawl": _reachable,
}


def default_value(kind: str) -> str:
    """What a check runs against when the variable is unset: only ollama has a default."""
    return ollama_base_url({}) if kind == "ollama" else ""


async def run_check(kind: str, value: str, client: httpx.AsyncClient) -> dict[str, Any]:
    try:
        result = await CHECKS[kind](client, value)
    except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
        result = _result(False, t.CHECK_UNREACHABLE.format(error=str(exc) or type(exc).__name__))
    if kind in SECRET_KINDS:
        result["detail"] = result["detail"].replace(value, "…")
    return result
