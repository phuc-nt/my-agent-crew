"""Web tools. `fetch_url` refuses private addresses, does not follow redirects on its
own (the model sees the hop and may ask again) and reads a page only as far as
`web_fetch` allows. An address the agent put together itself stops for a person
(`outbound.py`), and what a page answers stands inside the fence a browser tool puts around
a page. `web_search` always exists because
DuckDuckGo needs no key; keys and a firecrawl host only change which backend answers
first, and the model key adds a paid backend for when DuckDuckGo turns a script away."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from collections.abc import Callable
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

import httpx

from my_agent_crew import texts
from my_agent_crew.browser.fence import answer, room
from my_agent_crew.config import Settings
from my_agent_crew.tools.outbound import Seen, composed_reason
from my_agent_crew.tools.registry import Tool, ToolError
from my_agent_crew.tools.web_fetch import fetch_page
from my_agent_crew.tools.web_providers import firecrawl_scrape
from my_agent_crew.tools.web_search import run_search, search_backends

# `search_backends` lived here before the search moved out; callers still import it here.
__all__ = ["build_web_tools", "search_backends"]

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
    settings: Settings,
    client: httpx.AsyncClient,
    resolver: Resolver = resolve_host,
    seen: Seen | None = None,
) -> list[Tool]:
    """`seen` is what the turn's conversation was handed from outside the model; without it
    every address outside the agent's `outbound_hosts` is taken as one the agent wrote."""
    limit = settings.tool_output_chars
    size = room(limit, texts.URL_PART.format(start=10**6, end=10**6, total=10**6))

    def page(body: str, start: int) -> str:
        """Whatever a server answered is data: its words, and where a redirect points. What
        the agent's cap has no room for is read by asking again from where this part ends:
        cut by the registry, the fence would lose its closing line."""
        part = body[start : start + size]
        whole = len(part) == len(body)
        told = texts.URL_PART.format(start=start, end=start + len(part), total=len(body))
        return answer(limit, [] if whole else [told], part)

    async def fetch_url(args: dict[str, Any]) -> str:
        url, start = str(args["url"]), max(0, int(args.get("offset") or 0))
        await _guard_url(url, resolver)
        if settings.firecrawl_base_url:
            markdown = await _scrape(settings, client, url)
            if markdown.strip():
                return page(markdown[:MAX_MARKDOWN_CHARS], start)
        body, content_type = await fetch_page(client, url)
        if "html" in content_type:
            body = html_to_text(body)
        if not body.strip():
            # An empty answer reads to the model as "the page says nothing".
            raise ToolError(texts.URL_EMPTY_BODY)
        return page(body[:MAX_PAGE_CHARS], start)

    def asks(args: dict[str, Any]) -> str | None:
        return composed_reason(str(args.get("url", "")), settings.outbound_hosts, seen)

    async def web_search(args: dict[str, Any]) -> str:
        query = str(args["query"])
        results, error = await run_search(settings, client, query)
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
                "properties": {
                    "url": {"type": "string"},
                    "offset": {
                        "type": "integer",
                        "description": "Đọc tiếp từ ký tự này khi trang dài hơn một lần trả.",
                    },
                },
                "required": ["url"],
            },
            run=fetch_url,
            # Asked of the gate for one thing only: an address the agent wrote itself. Every
            # other call is routine, in a supervised conversation as in an autonomous one.
            # A call a person may have to allow is not made again by a restart on its own.
            requires_approval=True,
            ask_when=asks,
            allow_when=lambda args: asks(args) is None,
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
            replay_safe=True,
        ),
    ]
    return tools


async def _scrape(settings: Settings, client: httpx.AsyncClient, url: str) -> str:
    """A scrape that fails is not an error: `fetch_url` just falls back to raw text."""
    try:
        return await firecrawl_scrape(
            client, settings.firecrawl_base_url, settings.firecrawl_api_key, url
        )
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("fetch_url: firecrawl scrape failed (%s), using plain text", exc)
        return ""
