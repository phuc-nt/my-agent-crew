import json

import httpx
import pytest

from my_agent_crew.llm.openrouter import OpenRouterProvider, to_wire, tools_to_wire
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.llm.types import Completion, Message, TextDelta, ToolCall, ToolSpec
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
    return OpenRouterProvider("test-key", client)


async def test_text_stream_assembles_content_and_cost():
    captured: list[httpx.Request] = []
    body = sse(
        delta("Xin "),
        delta("chào"),
        delta(finish="stop"),
        {"usage": {"prompt_tokens": 10, "completion_tokens": 2, "cost": 0.00042}},
    )
    p = provider_with(body, capture=captured)
    items = await collect(p.stream([Message(role="user", content="hi")], [], "x/y"))
    assert [i.text for i in items if isinstance(i, TextDelta)] == ["Xin ", "chào"]
    done = items[-1]
    assert isinstance(done, Completion)
    assert done.message.content == "Xin chào"
    assert done.usage.cost_usd == pytest.approx(0.00042)
    assert done.model == "x/y" and done.provider == "openrouter"
    sent = json.loads(captured[0].content)
    assert sent["stream"] is True and sent["usage"] == {"include": True}
    assert captured[0].headers["authorization"] == "Bearer test-key"


async def test_missing_cost_is_reported_as_unknown_not_zero():
    body = sse(delta("ok"), {"usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    items = await collect(provider_with(body).stream([Message(role="user", content="hi")], [], "m"))
    assert items[-1].usage.cost_usd is None


async def test_fragmented_tool_call_arguments_are_reassembled():
    body = sse(
        delta(tool_calls=[{"index": 0, "id": "c1", "function": {"name": "workspace_read"}}]),
        delta(tool_calls=[{"index": 0, "function": {"arguments": '{"pa'}}]),
        delta(tool_calls=[{"index": 0, "function": {"arguments": 'th": "a.txt"}'}}]),
        delta(finish="tool_calls"),
    )
    items = await collect(provider_with(body).stream([Message(role="user", content="hi")], [], "m"))
    done = items[-1]
    assert done.message.tool_calls == (ToolCall("c1", "workspace_read", {"path": "a.txt"}),)
    assert done.finish_reason == "tool_calls"


async def test_malformed_tool_arguments_raise_provider_error():
    body = sse(
        delta(tool_calls=[{"index": 0, "id": "c1", "function": {"name": "t", "arguments": "{"}}]),
        delta(finish="tool_calls"),
    )
    with pytest.raises(ProviderError):
        await collect(provider_with(body).stream([Message(role="user", content="hi")], [], "m"))


async def test_http_error_status_raises_provider_error():
    p = provider_with('{"error": {"message": "no credit"}}', status=402)
    with pytest.raises(ProviderError, match="402"):
        await collect(p.stream([Message(role="user", content="hi")], [], "m"))


async def test_error_chunk_inside_stream_raises():
    body = sse({"error": {"message": "rate limited"}})
    with pytest.raises(ProviderError, match="rate limited"):
        await collect(provider_with(body).stream([Message(role="user", content="hi")], [], "m"))


async def test_transport_failure_raises_provider_error():
    def handler(request):
        raise httpx.ConnectError("refused")

    p = OpenRouterProvider("k", httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(ProviderError):
        await collect(p.stream([Message(role="user", content="hi")], [], "m"))


def test_wire_format_round_trips_tool_messages():
    msgs = [
        Message(role="system", content="s"),
        Message(
            role="assistant",
            content="",
            tool_calls=(ToolCall("c1", "workspace_read", {"path": "a"}),),
        ),
        Message(role="tool", content="data", tool_call_id="c1", name="workspace_read"),
    ]
    wire = to_wire(msgs)
    assert wire[1]["tool_calls"][0]["function"] == {
        "name": "workspace_read",
        "arguments": '{"path": "a"}',
    }
    assert wire[2] == {
        "role": "tool",
        "content": "data",
        "tool_call_id": "c1",
        "name": "workspace_read",
    }
    spec = ToolSpec("t", "desc", {"type": "object"})
    assert tools_to_wire([spec])[0]["function"]["parameters"] == {"type": "object"}
