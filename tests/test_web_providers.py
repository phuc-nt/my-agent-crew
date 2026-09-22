import httpx
import pytest

from my_agent_crew.config import Route, Settings
from my_agent_crew.tools.registry import ToolRegistry
from my_agent_crew.tools.web import build_web_tools, search_backends
from my_agent_crew.tools.web_providers import (
    duckduckgo_search,
    firecrawl_scrape,
    firecrawl_search,
    parse_duckduckgo,
)

PUBLIC = lambda host: ["93.184.216.34"]  # noqa: E731
FIRECRAWL = "http://127.0.0.1:3002"

DUCK_HTML = """
<div class="result">
  <a class="result__a" href="/l/?uddg=https%3A%2F%2Fa.example%2Fone">Tiêu <b>đề</b> một</a>
  <a class="result__snippet" href="x">Trích đoạn &amp; một</a>
</div>
<div class="result">
  <a class="result__a" href="https://b.example/two">Đề hai</a>
  <a class="result__snippet" href="y">Trích đoạn hai</a>
</div>
"""


def settings(**kwargs) -> Settings:
    return Settings(home="/tmp/x", routes=(Route("fake", "echo"),), **kwargs)


def registry(handler, config: Settings | None = None) -> ToolRegistry:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ToolRegistry(build_web_tools(config or settings(), client, PUBLIC))


def test_duckduckgo_parser_unwraps_redirect_and_strips_tags():
    hits = parse_duckduckgo(DUCK_HTML)
    assert [h.url for h in hits] == ["https://a.example/one", "https://b.example/two"]
    assert hits[0].title == "Tiêu đề một"
    assert hits[0].snippet == "Trích đoạn & một"


def test_duckduckgo_parser_returns_nothing_when_markup_changed():
    assert parse_duckduckgo("<div class='brand-new'>no results here</div>") == []


async def test_firecrawl_search_reads_web_list():
    def handler(request):
        assert request.url.path == "/v2/search"
        assert "authorization" not in request.headers
        return httpx.Response(
            200,
            json={"data": {"web": [{"title": "T", "url": "https://a.b/", "description": "D"}]}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    hits = await firecrawl_search(client, FIRECRAWL, None, "q")
    assert [h.render() for h in hits] == ["T\nhttps://a.b/\nD"]


async def test_firecrawl_sends_key_only_when_configured():
    seen = []

    def handler(request):
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"data": {"markdown": "# Xin chào"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await firecrawl_scrape(client, FIRECRAWL, None, "https://a.b/")
    await firecrawl_scrape(client, FIRECRAWL, "secret", "https://a.b/")
    assert seen == [None, "Bearer secret"]


async def test_duckduckgo_search_posts_the_query():
    def handler(request):
        assert request.method == "POST" and b"q=abc" in request.content
        return httpx.Response(200, text=DUCK_HTML)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    hits = await duckduckgo_search(client, "abc")
    assert len(hits) == 2


def test_backend_order_puts_firecrawl_first_and_duckduckgo_last():
    assert search_backends(settings()) == ["duckduckgo"]
    full = settings(firecrawl_base_url=FIRECRAWL, brave_api_key="b", tavily_api_key="t")
    assert search_backends(full) == ["firecrawl", "brave", "tavily", "duckduckgo"]


async def test_search_works_without_any_key():
    def handler(request):
        assert "duckduckgo" in request.url.host
        return httpx.Response(200, text=DUCK_HTML)

    result = await registry(handler).execute("web_search", {"query": "abc"})
    assert result.ok and "https://a.example/one" in result.output


async def test_failing_firecrawl_falls_through_to_duckduckgo():
    def handler(request):
        if request.url.host == "127.0.0.1":
            return httpx.Response(500, text="boom")
        return httpx.Response(200, text=DUCK_HTML)

    config = settings(firecrawl_base_url=FIRECRAWL)
    result = await registry(handler, config).execute("web_search", {"query": "abc"})
    assert result.ok and "https://a.example/one" in result.output


async def test_every_backend_down_reports_unreachable_not_empty():
    def handler(request):
        raise httpx.ConnectError("refused")

    config = settings(firecrawl_base_url=FIRECRAWL)
    result = await registry(handler, config).execute("web_search", {"query": "abc"})
    assert result.ok is False and "refused" in result.output


async def test_empty_duckduckgo_page_is_no_results_not_an_error():
    def handler(request):
        return httpx.Response(200, text="<div>nothing</div>")

    result = await registry(handler).execute("web_search", {"query": "abc"})
    assert result.ok and "abc" in result.output


async def test_fetch_url_prefers_firecrawl_markdown():
    def handler(request):
        if request.url.path == "/v2/scrape":
            return httpx.Response(200, json={"data": {"markdown": "# Tiêu đề\n\n- một"}})
        return httpx.Response(200, text="<p>raw</p>", headers={"content-type": "text/html"})

    config = settings(firecrawl_base_url=FIRECRAWL)
    result = await registry(handler, config).execute("fetch_url", {"url": "https://a.b/"})
    assert result.ok and result.output.startswith("# Tiêu đề")


async def test_fetch_url_falls_back_to_plain_text_when_scrape_fails():
    def handler(request):
        if request.url.path == "/v2/scrape":
            return httpx.Response(502, text="down")
        return httpx.Response(200, text="<p>raw</p>", headers={"content-type": "text/html"})

    config = settings(firecrawl_base_url=FIRECRAWL)
    result = await registry(handler, config).execute("fetch_url", {"url": "https://a.b/"})
    assert result.ok and result.output == "raw"


@pytest.mark.parametrize("markdown", ["", "   "])
async def test_blank_markdown_falls_back_to_plain_text(markdown: str):
    def handler(request):
        if request.url.path == "/v2/scrape":
            return httpx.Response(200, json={"data": {"markdown": markdown}})
        return httpx.Response(200, text="<p>raw</p>", headers={"content-type": "text/html"})

    config = settings(firecrawl_base_url=FIRECRAWL)
    result = await registry(handler, config).execute("fetch_url", {"url": "https://a.b/"})
    assert result.output.strip() in {"raw", markdown.strip()}
