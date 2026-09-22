"""The ollama provider: same OpenAI-compatible wire as OpenRouter, no key, no price, and
a base url that a standard install does not have to configure."""

import json

import httpx
import pytest

from my_agent_crew.llm.ollama import DEFAULT_BASE_URL, OllamaProvider, base_url
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.llm.types import Completion, Message, TextDelta, ToolSpec
from tests.conftest import collect


def sse(*chunks: dict) -> str:
    return "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"


def delta(content=None, tool_calls=None, finish=None):
    d: dict = {}
    if content is not None:
        d["content"] = content
    if tool_calls is not None:
        d["tool_calls"] = tool_calls
    return {"choices": [{"delta": d, "finish_reason": finish}]}


def provider_with(body: str, status: int = 200, capture: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        return httpx.Response(status, text=body, headers={"content-type": "text/event-stream"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OllamaProvider(client=client)


def test_a_standard_install_needs_no_configuration():
    assert base_url({}) == DEFAULT_BASE_URL
    assert base_url({"OLLAMA_BASE_URL": "  "}) == DEFAULT_BASE_URL
    assert base_url({"OLLAMA_BASE_URL": "http://box:11434/v1"}) == "http://box:11434/v1"


async def test_text_streams_back_and_reports_the_provider():
    p = provider_with(sse(delta("Xin "), delta("chào"), delta(finish="stop")))
    items = await collect(p.stream([Message(role="user", content="hi")], [], "qwen3:8b"))
    assert [i.text for i in items if isinstance(i, TextDelta)] == ["Xin ", "chào"]
    done = items[-1]
    assert isinstance(done, Completion)
    assert done.provider == "ollama" and done.model == "qwen3:8b"
    assert done.message.content == "Xin chào"


async def test_a_local_model_reports_no_price_rather_than_zero():
    """Zero and unknown are different claims: a run that spent nothing and a run whose cost
    we could not read must not look the same on the card."""
    p = provider_with(sse(delta("ok"), delta(finish="stop")))
    items = await collect(p.stream([Message(role="user", content="hi")], [], "qwen3:8b"))
    assert items[-1].usage.cost_usd is None


def test_no_key_is_sent_to_a_server_on_this_machine():
    captured: list[httpx.Request] = []
    p = provider_with(sse(delta("ok"), delta(finish="stop")), capture=captured)
    import asyncio

    asyncio.run(collect(p.stream([Message(role="user", content="hi")], [], "m")))
    assert "authorization" not in {k.lower() for k in captured[0].headers}


async def test_tool_calls_come_back_assembled():
    body = sse(
        delta(
            tool_calls=[
                {"index": 0, "id": "c1", "function": {"name": "workspace_list", "arguments": '{"p'}}
            ]
        ),
        delta(tool_calls=[{"index": 0, "function": {"arguments": 'ath": "."}'}}]),
        delta(finish="tool_calls"),
    )
    p = provider_with(body)
    spec = ToolSpec(name="workspace_list", description="d", parameters={"type": "object"})
    items = await collect(p.stream([Message(role="user", content="hi")], [spec], "m"))
    calls = items[-1].message.tool_calls
    assert len(calls) == 1
    assert calls[0].name == "workspace_list" and calls[0].arguments == {"path": "."}


async def test_a_server_that_is_not_running_is_a_provider_error_not_a_crash():
    """Nothing listening is the normal case on a machine without ollama, and it has to fall
    through to the next route rather than take the turn down."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    p = OllamaProvider(client=client)
    with pytest.raises(ProviderError):
        await collect(p.stream([Message(role="user", content="hi")], [], "m"))


async def test_an_http_error_names_the_model():
    p = provider_with("nope", status=500)
    with pytest.raises(ProviderError, match="qwen3:8b"):
        await collect(p.stream([Message(role="user", content="hi")], [], "qwen3:8b"))


def test_the_url_keeps_one_slash_between_base_and_path():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            text=sse(delta("ok"), delta(finish="stop")),
            headers={"content-type": "text/event-stream"},
        )

    import asyncio

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    p = OllamaProvider(url="http://127.0.0.1:11434/v1/", client=client)
    asyncio.run(collect(p.stream([Message(role="user", content="hi")], [], "m")))
    assert str(captured[0].url) == "http://127.0.0.1:11434/v1/chat/completions"
