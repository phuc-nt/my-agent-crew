import httpx
import pytest

from my_agent_crew import texts
from my_agent_crew.config import Route, Settings
from my_agent_crew.tools.registry import ToolRegistry
from my_agent_crew.tools.web import build_web_tools, html_to_text

PUBLIC = lambda host: ["93.184.216.34"]  # noqa: E731
PRIVATE = lambda host: ["10.0.0.5"]  # noqa: E731


def registry(handler, settings: Settings | None = None, resolver=PUBLIC) -> ToolRegistry:
    settings = settings or Settings(home="/tmp/x", routes=(Route("fake", "echo"),))
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ToolRegistry(build_web_tools(settings, client, resolver))


def test_html_to_text_drops_scripts_and_tags():
    html = "<html><script>evil()</script><h1>Tiêu đề</h1><p>Nội <b>dung</b></p></html>"
    assert html_to_text(html) == "Tiêu đề\nNội\ndung"


async def test_fetch_public_page_returns_text():
    def handler(request):
        return httpx.Response(200, text="<p>hello</p>", headers={"content-type": "text/html"})

    result = await registry(handler).execute("fetch_url", {"url": "https://example.com/"})
    assert result.ok and result.output == "hello"


async def test_private_address_is_refused_before_any_request():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, text="x")

    result = await registry(handler, resolver=PRIVATE).execute(
        "fetch_url", {"url": "http://intranet.local/"}
    )
    assert result.ok is False and texts.URL_PRIVATE in result.output
    assert calls == []


async def test_non_http_scheme_refused():
    result = await registry(lambda r: httpx.Response(200)).execute(
        "fetch_url", {"url": "file:///etc/passwd"}
    )
    assert result.ok is False and texts.URL_SCHEME in result.output


async def test_redirect_is_reported_not_followed():
    def handler(request):
        return httpx.Response(302, headers={"location": "http://10.0.0.1/admin"})

    result = await registry(handler).execute("fetch_url", {"url": "https://example.com/"})
    assert result.ok and "http://10.0.0.1/admin" in result.output


async def test_http_error_and_unreachable_are_distinct_messages():
    def status(request):
        return httpx.Response(503)

    def down(request):
        raise httpx.ConnectError("refused")

    a = await registry(status).execute("fetch_url", {"url": "https://example.com/"})
    b = await registry(down).execute("fetch_url", {"url": "https://example.com/"})
    assert "503" in a.output
    assert texts.URL_UNREACHABLE.split("{")[0] in b.output


def test_web_search_exists_without_any_key():
    """DuckDuckGo closes the backend list, so a machine with no search key still has
    the tool rather than an agent that silently lost it."""
    assert "web_search" in registry(lambda r: httpx.Response(200)).names()


async def test_search_empty_vs_unreachable_never_conflated():
    settings = Settings(home="/tmp/x", routes=(Route("fake", "echo"),), brave_api_key="k")

    def empty(request):
        if "duckduckgo" in request.url.host:
            return httpx.Response(200, text="<div>nothing</div>")
        return httpx.Response(200, json={"web": {"results": []}})

    def down(request):
        raise httpx.ConnectError("refused")

    a = await registry(empty, settings).execute("web_search", {"query": "abc"})
    b = await registry(down, settings).execute("web_search", {"query": "abc"})
    assert a.ok and a.output == texts.SEARCH_EMPTY.format(query="abc")
    assert b.ok is False and texts.SEARCH_UNREACHABLE.split("{")[0] in b.output


async def test_brave_results_are_formatted_with_url():
    settings = Settings(home="/tmp/x", routes=(Route("fake", "echo"),), brave_api_key="k")

    def handler(request):
        assert request.headers["x-subscription-token"] == "k"
        return httpx.Response(
            200,
            json={"web": {"results": [{"title": "T", "url": "https://a.b/", "description": "D"}]}},
        )

    result = await registry(handler, settings).execute("web_search", {"query": "q"})
    assert result.output == "T\nhttps://a.b/\nD"


@pytest.mark.parametrize("address", ["127.0.0.1", "192.168.1.1", "169.254.169.254", "::1"])
def test_private_ranges(address: str):
    from my_agent_crew.tools.web import is_private

    assert is_private(address)
