"""Which backend answers `web_search`, in what order, and what the tool reports when none
of them does."""

from __future__ import annotations

import logging
from collections.abc import Awaitable

import httpx

from my_agent_crew.config import Settings
from my_agent_crew.tools.web_openrouter import openrouter_search
from my_agent_crew.tools.web_providers import (
    SearchHit,
    brave_search,
    duckduckgo_search,
    firecrawl_search,
    tavily_search,
)

logger = logging.getLogger(__name__)


def search_backends(settings: Settings) -> list[str]:
    """Priority order, best first. DuckDuckGo is always there, so the list is never empty;
    OpenRouter, which charges per search, comes after it."""
    names = []
    if settings.firecrawl_base_url:
        names.append("firecrawl")
    if settings.brave_api_key:
        names.append("brave")
    if settings.tavily_api_key:
        names.append("tavily")
    names.append("duckduckgo")
    if settings.openrouter_api_key:
        names.append("openrouter")
    return names


def _provider(
    name: str, settings: Settings, client: httpx.AsyncClient, query: str
) -> Awaitable[list[SearchHit]]:
    if name == "firecrawl":
        base, key = settings.firecrawl_base_url, settings.firecrawl_api_key
        return firecrawl_search(client, base, key, query)
    if name == "brave":
        return brave_search(client, settings.brave_api_key or "", query)
    if name == "tavily":
        return tavily_search(client, settings.tavily_api_key or "", query)
    if name == "openrouter":
        return openrouter_search(client, settings.openrouter_api_key or "", query)
    return duckduckgo_search(client, query)


async def run_search(
    settings: Settings, client: httpx.AsyncClient, query: str
) -> tuple[list[SearchHit], str | None]:
    """Try each backend in turn. A backend that fails is logged and skipped. One that
    answered with nothing makes the search empty rather than failed; only when every one
    of them failed is the service unreachable, and the error then names each backend, so
    the model does not blame the first one for the last one's failure."""
    failures: list[str] = []
    answered = False
    for name in search_backends(settings):
        try:
            hits = await _provider(name, settings, client, query)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("web_search: %s failed (%s), trying the next backend", name, exc)
            failures.append(f"{name}: {exc}")
            continue
        if hits:
            return hits, None
        answered = True
    return [], None if answered else "; ".join(failures)
