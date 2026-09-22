"""Search and scrape backends behind `web_search` and `fetch_url`.

Each provider is one async function returning hits, or an empty list when it has
nothing to say. A provider that is down raises; the caller decides whether to try the
next one. DuckDuckGo needs no key, so a machine with no search key still searches.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import parse_qs, urlsplit

import httpx

MAX_HITS = 5
SEARCH_TIMEOUT = 20.0
SCRAPE_TIMEOUT = 30.0
DUCKDUCKGO_URL = "https://html.duckduckgo.com/html/"
# DuckDuckGo's HTML endpoint answers a browser; a bare client gets an empty page.
BROWSER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120"


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str

    def render(self) -> str:
        return f"{self.title}\n{self.url}\n{self.snippet}"


def _headers(api_key: str | None) -> dict[str, str]:
    """A self-hosted firecrawl needs no key; only send one when it exists so a wrong
    base url cannot leak a token to a stranger."""
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


async def firecrawl_search(
    client: httpx.AsyncClient, base_url: str, api_key: str | None, query: str
) -> list[SearchHit]:
    resp = await client.post(
        f"{base_url.rstrip('/')}/v2/search",
        json={"query": query, "limit": MAX_HITS},
        headers=_headers(api_key),
        timeout=SEARCH_TIMEOUT,
    )
    resp.raise_for_status()
    payload = resp.json().get("data") or {}
    items = payload.get("web") if isinstance(payload, dict) else payload
    return [
        SearchHit(i.get("title", ""), i.get("url", ""), i.get("description", ""))
        for i in (items or [])[:MAX_HITS]
    ]


async def firecrawl_scrape(
    client: httpx.AsyncClient, base_url: str, api_key: str | None, url: str
) -> str:
    """Markdown for the model instead of stripped tags: headings and lists survive."""
    resp = await client.post(
        f"{base_url.rstrip('/')}/v2/scrape",
        json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
        headers=_headers(api_key),
        timeout=SCRAPE_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json().get("data") or {}
    return str(data.get("markdown") or "")


async def brave_search(client: httpx.AsyncClient, api_key: str, query: str) -> list[SearchHit]:
    resp = await client.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": MAX_HITS},
        headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        timeout=SEARCH_TIMEOUT,
    )
    resp.raise_for_status()
    items = (resp.json().get("web") or {}).get("results") or []
    return [
        SearchHit(i.get("title", ""), i.get("url", ""), i.get("description", ""))
        for i in items[:MAX_HITS]
    ]


async def tavily_search(client: httpx.AsyncClient, api_key: str, query: str) -> list[SearchHit]:
    resp = await client.post(
        "https://api.tavily.com/search",
        json={"api_key": api_key, "query": query, "max_results": MAX_HITS},
        timeout=SEARCH_TIMEOUT,
    )
    resp.raise_for_status()
    items = resp.json().get("results") or []
    return [
        SearchHit(i.get("title", ""), i.get("url", ""), i.get("content", ""))
        for i in items[:MAX_HITS]
    ]


_ANCHOR = re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_SNIPPET = re.compile(r'class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', re.S)
_TAGS = re.compile(r"<[^>]+>")


def _clean(fragment: str) -> str:
    return unescape(_TAGS.sub("", fragment)).strip()


def _direct_url(href: str) -> str:
    """DuckDuckGo wraps every result in /l/?uddg=<encoded>; give the model the real one."""
    if "uddg=" not in href:
        return href if href.startswith("http") else f"https:{href}"
    target = parse_qs(urlsplit(href).query).get("uddg")
    return target[0] if target else href


def parse_duckduckgo(html: str) -> list[SearchHit]:
    """Markup drift makes this return nothing, never raise: the tool then says
    "no results" rather than pretending the service is down."""
    snippets = _SNIPPET.findall(html)
    hits = []
    for index, (href, title) in enumerate(_ANCHOR.findall(html)[:MAX_HITS]):
        snippet = _clean(snippets[index]) if index < len(snippets) else ""
        hits.append(SearchHit(_clean(title), _direct_url(href), snippet))
    return hits


async def duckduckgo_search(client: httpx.AsyncClient, query: str) -> list[SearchHit]:
    resp = await client.post(
        DUCKDUCKGO_URL,
        data={"q": query},
        headers={"User-Agent": BROWSER_AGENT},
        timeout=SEARCH_TIMEOUT,
    )
    resp.raise_for_status()
    return parse_duckduckgo(resp.text)
