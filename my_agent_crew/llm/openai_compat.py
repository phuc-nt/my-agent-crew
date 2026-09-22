"""The OpenAI-compatible chat API, shared by every provider that speaks it.

OpenRouter and a local ollama differ in three things: the base url, whether a key is sent,
and whether the stream reports a price. Everything else — the wire shape of messages and
tools, the fragmented tool_call deltas, the `data:` stream framing — is the same, and was
duplicated once before this module existed.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.llm.types import (
    Completion,
    Message,
    StreamItem,
    TextDelta,
    ToolCall,
    ToolSpec,
    Usage,
)


def _content(m: Message) -> str | list[dict[str, Any]]:
    """Plain text unless the message carries pictures; then the OpenAI parts form, text
    first so the model reads the question before the image."""
    if not m.images:
        return m.content
    parts: list[dict[str, Any]] = [{"type": "text", "text": m.content}] if m.content else []
    parts += [{"type": "image_url", "image_url": {"url": url}} for url in m.images]
    return parts


def to_wire(messages: Sequence[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        item: dict[str, Any] = {"role": m.role, "content": _content(m)}
        if m.tool_calls:
            item["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                }
                for tc in m.tool_calls
            ]
        if m.role == "tool":
            item["tool_call_id"] = m.tool_call_id
            if m.name:
                item["name"] = m.name
        out.append(item)
    return out


def tools_to_wire(tools: Sequence[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
        }
        for t in tools
    ]


class ToolCallBuffer:
    """Assembles fragmented tool_call deltas keyed by their stream index."""

    def __init__(self) -> None:
        self._parts: dict[int, dict[str, str]] = {}

    def feed(self, deltas: list[dict[str, Any]]) -> None:
        for d in deltas:
            slot = self._parts.setdefault(d.get("index", 0), {"id": "", "name": "", "args": ""})
            slot["id"] = d.get("id") or slot["id"]
            fn = d.get("function") or {}
            slot["name"] = fn.get("name") or slot["name"]
            slot["args"] += fn.get("arguments") or ""

    def calls(self) -> tuple[ToolCall, ...]:
        calls = []
        for index in sorted(self._parts):
            slot = self._parts[index]
            try:
                args = json.loads(slot["args"] or "{}")
            except ValueError as exc:
                raise ProviderError(f"tool call {slot['name']} had malformed arguments") from exc
            if not isinstance(args, dict):
                raise ProviderError(f"tool call {slot['name']} arguments are not an object")
            calls.append(
                ToolCall(id=slot["id"] or f"call_{index}", name=slot["name"], arguments=args)
            )
        return tuple(calls)


def usage_from(raw: dict[str, Any]) -> Usage:
    cost = raw.get("cost")
    return Usage(
        prompt_tokens=int(raw.get("prompt_tokens") or 0),
        completion_tokens=int(raw.get("completion_tokens") or 0),
        cost_usd=float(cost) if cost is not None else None,
    )


async def stream_chat(
    client: httpx.AsyncClient,
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    provider: str,
    model: str,
) -> AsyncIterator[StreamItem]:
    """One streamed completion: text deltas as they arrive, then a final `Completion`."""
    text_parts: list[str] = []
    calls = ToolCallBuffer()
    usage = Usage()
    finish = "stop"
    try:
        async with client.stream("POST", url, json=body, headers=headers) as resp:
            if resp.status_code >= 400:
                raise ProviderError(f"HTTP {resp.status_code} from {model}")
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                chunk = json.loads(payload)
                if "error" in chunk:
                    raise ProviderError(str(chunk["error"]))
                if chunk.get("usage"):
                    usage = usage_from(chunk["usage"])
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        text_parts.append(delta["content"])
                        yield TextDelta(delta["content"])
                    if delta.get("tool_calls"):
                        calls.feed(delta["tool_calls"])
                    finish = choice.get("finish_reason") or finish
    except httpx.HTTPError as exc:
        raise ProviderError(f"transport failure talking to {model}: {exc}") from exc
    except ValueError as exc:
        raise ProviderError(f"malformed stream from {model}") from exc
    message = Message(role="assistant", content="".join(text_parts), tool_calls=calls.calls())
    yield Completion(
        message=message, usage=usage, provider=provider, model=model, finish_reason=finish
    )
