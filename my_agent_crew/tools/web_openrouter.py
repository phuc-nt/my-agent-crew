"""Web search through OpenRouter's web plugin, for a machine whose only key is the model key.

DuckDuckGo's keyless pages answer scripts with a bot check more often than not, so a home
with no search key had no search at all. The plugin (Exa) costs about $0.007 a search plus
a short completion, which is why `web_search` tries it only after the free backends.

The hits are the url_citation annotations OpenRouter attaches to the answer. A model that
cites in its text instead of through annotations is read for markdown links.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from my_agent_crew.tools.web_providers import MAX_HITS, SEARCH_TIMEOUT, SearchHit

OPENROUTER_SEARCH_URL = "https://openrouter.ai/api/v1/chat/completions"
# The engine's default chat model: cheap, and already the one a home pays for.
SEARCH_MODEL = "deepseek/deepseek-v4-flash"
SNIPPET_CHARS = 300
PROMPT = (
    "Search the web for: {query}\n"
    "List the most relevant results, one line each, as a markdown link [title](url) "
    "followed by one sentence on what the page says. No other text."
)
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)\s*[-:–—]?\s*([^\n]*)")


def _snippet(text: Any) -> str:
    return " ".join(str(text or "").split())[:SNIPPET_CHARS]


def parse_openrouter(payload: dict[str, Any]) -> list[SearchHit]:
    choices = payload.get("choices") or []
    message = (choices[0].get("message") if choices else None) or {}
    hits: list[SearchHit] = []
    seen: set[str] = set()
    for note in message.get("annotations") or []:
        cite = note.get("url_citation") or {}
        url = cite.get("url") or ""
        if note.get("type") == "url_citation" and url and url not in seen:
            seen.add(url)
            hits.append(SearchHit(cite.get("title") or url, url, _snippet(cite.get("content"))))
    if not hits:
        for title, url, rest in _LINK.findall(message.get("content") or ""):
            if url not in seen:
                seen.add(url)
                hits.append(SearchHit(title.strip(), url, _snippet(rest)))
    return hits[:MAX_HITS]


async def openrouter_search(client: httpx.AsyncClient, api_key: str, query: str) -> list[SearchHit]:
    resp = await client.post(
        OPENROUTER_SEARCH_URL,
        json={
            "model": SEARCH_MODEL,
            "messages": [{"role": "user", "content": PROMPT.format(query=query)}],
            "plugins": [{"id": "web", "engine": "exa", "max_results": MAX_HITS}],
            "max_tokens": 600,
        },
        headers={"Authorization": f"Bearer {api_key}"},
        # A search and a completion, so twice a plain search's budget.
        timeout=SEARCH_TIMEOUT * 2,
    )
    resp.raise_for_status()
    return parse_openrouter(resp.json())
