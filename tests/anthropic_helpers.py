"""A fake Claude Messages stream for the provider tests: events as the API sends them."""

import json

import httpx

from my_agent_crew.llm.anthropic import AnthropicProvider
from my_agent_crew.llm.types import Message

KEY = "test-anthropic-key"
HI = [Message(role="system", content="sys"), Message(role="user", content="hi")]


def sse(*events: dict) -> str:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)


def start(**usage) -> dict:
    return {"type": "message_start", "message": {"usage": {"input_tokens": 10, **usage}}}


def block(index: int, **content) -> dict:
    return {"type": "content_block_start", "index": index, "content_block": content}


def delta(index: int, **d) -> dict:
    return {"type": "content_block_delta", "index": index, "delta": d}


def end(stop: str, output: int = 5) -> list[dict]:
    return [
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop},
            "usage": {"output_tokens": output},
        },
        {"type": "message_stop"},
    ]


def provider_with(body: str, status: int = 200, capture: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        return httpx.Response(status, text=body, headers={"content-type": "text/event-stream"})

    return AnthropicProvider(KEY, httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def error_body(kind: str, message: str) -> str:
    return json.dumps({"type": "error", "error": {"type": kind, "message": message}})
