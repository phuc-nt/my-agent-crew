"""Web tools. `fetch_url` refuses private addresses and does not follow redirects on
its own (the model sees the hop and may ask again). `web_search` is registered only
when a search key exists, so "no key" and "no results" can never be confused."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Callable
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

import httpx

from my_agent_crew import texts
from my_agent_crew.config import Settings
from my_agent_crew.tools.registry import Tool, ToolError

MAX_PAGE_CHARS = 6000
Resolver = Callable[[str], list[str]]


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
        try:
            resp = await client.get(url, follow_redirects=False, timeout=20.0)
        except httpx.HTTPError as exc:
            raise ToolError(texts.URL_UNREACHABLE.format(error=exc)) from exc
        if 300 <= resp.status_code < 400:
            return texts.URL_REDIRECT.format(location=resp.headers.get("location", "?"))
        if resp.status_code >= 400:
            raise ToolError(texts.URL_STATUS.format(status=resp.status_code))
        body = resp.text
        if "html" in resp.headers.get("content-type", ""):
            body = html_to_text(body)
        return body[:MAX_PAGE_CHARS]

    async def web_search(args: dict[str, Any]) -> str:
        query = str(args["query"])
        try:
            results = await _search(settings, client, query)
        except httpx.HTTPError as exc:
            raise ToolError(texts.SEARCH_UNREACHABLE.format(error=exc)) from exc
        if not results:
            return texts.SEARCH_EMPTY.format(query=query)
        return "\n\n".join(f"{t}\n{u}\n{s}" for t, u, s in results)

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
        )
    ]
    if settings.brave_api_key or settings.tavily_api_key:
        tools.append(
            Tool(
                name="web_search",
                description="Tìm kiếm web, trả về tiêu đề, URL và trích đoạn.",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                run=web_search,
            )
        )
    return tools


async def _search(
    settings: Settings, client: httpx.AsyncClient, query: str
) -> list[tuple[str, str, str]]:
    if settings.brave_api_key:
        resp = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": 5},
            headers={"X-Subscription-Token": settings.brave_api_key, "Accept": "application/json"},
            timeout=20.0,
        )
        resp.raise_for_status()
        items = (resp.json().get("web") or {}).get("results") or []
        return [(i.get("title", ""), i.get("url", ""), i.get("description", "")) for i in items]
    resp = await client.post(
        "https://api.tavily.com/search",
        json={"api_key": settings.tavily_api_key, "query": query, "max_results": 5},
        timeout=20.0,
    )
    resp.raise_for_status()
    items = resp.json().get("results") or []
    return [(i.get("title", ""), i.get("url", ""), i.get("content", "")) for i in items]
