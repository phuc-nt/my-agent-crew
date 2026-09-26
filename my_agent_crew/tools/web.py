"""Web tools. `fetch_url` refuses private addresses, does not follow redirects on its
own (the model sees the hop and may ask again) and reads a page only as far as
`web_fetch` allows. `web_search` always exists because
DuckDuckGo needs no key; keys and a firecrawl host only change which backend answers
first."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from collections.abc import Awaitable, Callable
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

import httpx

from my_agent_crew import texts
from my_agent_crew.config import Settings
from my_agent_crew.tools.registry import Tool, ToolError
from my_agent_crew.tools.web_fetch import fetch_page
from my_agent_crew.tools.web_providers import (
    SearchHit,
    brave_search,
    duckduckgo_search,
    firecrawl_scrape,
    firecrawl_search,
    tavily_search,
)

MAX_PAGE_CHARS = 6000
# Markdown from a scrape is already the main content, so it earns a longer budget than
# a whole HTML page stripped of tags.
MAX_MARKDOWN_CHARS = 20000
Resolver = Callable[[str], list[str]]
logger = logging.getLogger(__name__)


def resolve_host(host: str) -> list[str]:
    return [info[4][0] for info in socket.getaddrinfo(host, None)]


def is_private(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return "\n".join(parser.parts)


async def _guard_url(url: str, resolver: Resolver) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ToolError(texts.URL_SCHEME)
    try:
        addresses = await asyncio.to_thread(resolver, parts.hostname)
    except OSError as exc:
        raise ToolError(texts.URL_UNREACHABLE.format(error=exc)) from exc
    if not addresses or any(is_private(a) for a in addresses):
        raise ToolError(texts.URL_PRIVATE)


def build_web_tools(
    settings: Settings, client: httpx.AsyncClient, resolver: Resolver = resolve_host
) -> list[Tool]:
    async def fetch_url(args: dict[str, Any]) -> str:
        url = str(args["url"])
        await _guard_url(url, resolver)
        if settings.firecrawl_base_url:
            markdown = await _scrape(settings, client, url)
            if markdown:
                return markdown[:MAX_MARKDOWN_CHARS]
        body, content_type = await fetch_page(client, url)
        if "html" in content_type:
            body = html_to_text(body)
        return body[:MAX_PAGE_CHARS]

    async def web_search(args: dict[str, Any]) -> str:
        query = str(args["query"])
        results, error = await _search(settings, client, query)
        if error is not None and not results:
            raise ToolError(texts.SEARCH_UNREACHABLE.format(error=error))
        if not results:
            return texts.SEARCH_EMPTY.format(query=query)
        return "\n\n".join(hit.render() for hit in results)

    tools = [
        Tool(
            name="fetch_url",
            description="Tải nội dung văn bản của một trang web công khai.",
            parameters={
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
            run=fetch_url,
        ),
        Tool(
            name="web_search",
            description="Tìm kiếm web, trả về tiêu đề, URL và trích đoạn.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            run=web_search,
        ),
    ]
    return tools


def search_backends(settings: Settings) -> list[str]:
    """Priority order, best first. DuckDuckGo closes the list, so it is never empty."""
    names = []
    if settings.firecrawl_base_url:
        names.append("firecrawl")
    if settings.brave_api_key:
        names.append("brave")
    if settings.tavily_api_key:
        names.append("tavily")
    names.append("duckduckgo")
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
    return duckduckgo_search(client, query)


async def _search(
    settings: Settings, client: httpx.AsyncClient, query: str
) -> tuple[list[SearchHit], Exception | None]:
    """Try each backend in turn. A backend that fails is logged and skipped; only when
    every one of them failed does the tool report the search service as unreachable."""
    last: Exception | None = None
    for name in search_backends(settings):
        try:
            hits = await _provider(name, settings, client, query)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            logger.warning("web_search: %s failed (%s), trying the next backend", name, exc)
            last = exc
            continue
        if hits:
            return hits, None
    return [], last


async def _scrape(settings: Settings, client: httpx.AsyncClient, url: str) -> str:
    """A scrape that fails is not an error: `fetch_url` just falls back to raw text."""
    try:
        return await firecrawl_scrape(
            client, settings.firecrawl_base_url, settings.firecrawl_api_key, url
        )
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("fetch_url: firecrawl scrape failed (%s), using plain text", exc)
        return ""
