"""What `web_search` does when DuckDuckGo turns a script away, and the paid backend that
the model key brings in behind it."""

import json

import httpx
import pytest

from my_agent_crew import texts
from my_agent_crew.tools.web import search_backends
from my_agent_crew.tools.web_openrouter import SEARCH_MODEL, parse_openrouter
from my_agent_crew.tools.web_providers import SearchBlocked, duckduckgo_search
from tests.test_web_providers import DUCK_HTML, FIRECRAWL, registry, settings

BOT_CHECK = '<div class="anomaly-modal__box">Unfortunately, bots use DuckDuckGo too.</div>'
CITED = {
    "choices": [
        {
            "message": {
                "content": "[One](https://a.example/one) first",
                "annotations": [
                    {
                        "type": "url_citation",
                        "url_citation": {
                            "url": "https://a.example/one",
                            "title": "One",
                            "content": "Page   one",
                        },
                    },
                    {
                        "type": "url_citation",
                        "url_citation": {"url": "https://a.example/one", "title": "One again"},
                    },
                    {
                        "type": "url_citation",
                        "url_citation": {"url": "https://b.example/two", "title": "Two"},
                    },
                ],
            }
        }
    ]
}


def cloud(request: httpx.Request) -> httpx.Response | None:
    """The cloud's firecrawl scrapes but does not search; DuckDuckGo shows its puzzle."""
    if request.url.host == "127.0.0.1":
        return httpx.Response(501, json={"error": "search is not offered"})
    if "duckduckgo" in request.url.host:
        return httpx.Response(202, text=BOT_CHECK)
    return None


@pytest.mark.parametrize("status", [200, 202])
async def test_a_duckduckgo_bot_check_is_a_failure_not_an_empty_search(status: int):
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(status, text=BOT_CHECK))
    )
    with pytest.raises(SearchBlocked):
        await duckduckgo_search(client, "abc")


async def test_when_every_backend_fails_the_error_names_each_of_them():
    config = settings(firecrawl_base_url=FIRECRAWL)
    result = await registry(cloud, config).execute("web_search", {"query": "abc"})
    assert result.ok is False
    assert "firecrawl: " in result.output and "501" in result.output
    assert "duckduckgo: " in result.output and "bot check" in result.output


async def test_a_backend_that_answered_with_nothing_makes_the_search_empty_not_failed():
    def handler(request):
        if request.url.host == "127.0.0.1":
            return httpx.Response(501)
        return httpx.Response(200, text="<div>nothing</div>")

    result = await registry(handler, settings(firecrawl_base_url=FIRECRAWL)).execute(
        "web_search", {"query": "abc"}
    )
    assert result.ok and result.output == texts.SEARCH_EMPTY.format(query="abc")


def test_openrouter_searches_only_with_the_model_key_and_only_after_duckduckgo():
    assert "openrouter" not in search_backends(settings())
    keyed = settings(firecrawl_base_url=FIRECRAWL, brave_api_key="b", openrouter_api_key="or")
    assert search_backends(keyed) == ["firecrawl", "brave", "duckduckgo", "openrouter"]


async def test_a_blocked_duckduckgo_falls_through_to_openrouter():
    sent = []

    def handler(request):
        answer = cloud(request)
        if answer is not None:
            return answer
        sent.append(request)
        return httpx.Response(200, json=CITED)

    config = settings(firecrawl_base_url=FIRECRAWL, openrouter_api_key="or-key")
    result = await registry(handler, config).execute("web_search", {"query": "abc"})
    assert (
        result.ok
        and "https://a.example/one" in result.output
        and "https://b.example/two" in result.output
    )
    [request] = sent
    assert (
        request.url.host == "openrouter.ai" and request.headers["Authorization"] == "Bearer or-key"
    )
    body = json.loads(request.content)
    assert (
        body["model"] == SEARCH_MODEL
        and body["plugins"][0]["id"] == "web"
        and "abc" in body["messages"][0]["content"]
    )


async def test_duckduckgo_that_works_is_used_and_openrouter_is_not_paid_for():
    def handler(request):
        assert "openrouter" not in request.url.host
        return httpx.Response(200, text=DUCK_HTML)

    result = await registry(handler, settings(openrouter_api_key="k")).execute(
        "web_search", {"query": "abc"}
    )
    assert result.ok and "https://a.example/one" in result.output


def test_openrouter_hits_come_from_citations_once_each_or_else_from_links_in_the_text():
    hits = parse_openrouter(CITED)
    assert [(h.title, h.url, h.snippet) for h in hits] == [
        ("One", "https://a.example/one", "Page one"),
        ("Two", "https://b.example/two", ""),
    ]
    text = {
        "choices": [
            {"message": {"content": "- [Three](https://c.example/3) - says three\n- plain line"}}
        ]
    }
    assert [(h.title, h.url, h.snippet) for h in parse_openrouter(text)] == [
        ("Three", "https://c.example/3", "says three")
    ]
    assert parse_openrouter({"choices": []}) == [] and parse_openrouter({}) == []
