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
from my_agent_crew.llm.tool_call_buffer import ToolCallBuffer
from my_agent_crew.llm.types import (
    Completion,
    Message,
    ReasoningDelta,
    StreamItem,
    StreamStarted,
    TextDelta,
    ToolSpec,
    Usage,
)


def _content(m: Message) -> str | list[dict[str, Any]]:
    """Plain text unless the message carries pictures or audio; then the OpenAI parts
    form, text first so the model reads the question before what it sees or hears, then
    images, then audio."""
    if not m.images and not m.audio:
        return m.content
    parts: list[dict[str, Any]] = [{"type": "text", "text": m.content}] if m.content else []
    parts += [{"type": "image_url", "image_url": {"url": url}} for url in m.images]
    parts += [
        {"type": "input_audio", "input_audio": {"data": a.data, "format": a.format}}
        for a in m.audio
    ]
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


def usage_from(raw: dict[str, Any]) -> Usage:
    cost = raw.get("cost")
    thought = (raw.get("completion_tokens_details") or {}).get("reasoning_tokens")
    cached = (raw.get("prompt_tokens_details") or {}).get("cached_tokens")
    return Usage(
        prompt_tokens=int(raw.get("prompt_tokens") or 0),
        completion_tokens=int(raw.get("completion_tokens") or 0),
        cost_usd=float(cost) if cost is not None else None,
        reasoning_tokens=int(thought) if thought is not None else None,
        cached_tokens=int(cached) if cached is not None else None,
    )


def transient_status(code: object) -> bool:
    """A status that asking again may cure: a timeout, rate limit or upstream outage."""
    return isinstance(code, int) and (code in (408, 425, 429) or code >= 500)


def transient_error(error: object) -> bool:
    """An error chunk sent mid-stream, as OpenRouter does when the host behind it fails."""
    if not isinstance(error, dict):
        return False
    meta = error.get("metadata")
    if isinstance(meta, dict) and meta.get("error_type") == "provider_unavailable":
        return True
    return transient_status(error.get("code"))


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
    started = False
    try:
        async with client.stream("POST", url, json=body, headers=headers) as resp:
            if resp.status_code >= 400:
                raise ProviderError(
                    f"HTTP {resp.status_code} from {model}",
                    transient=transient_status(resp.status_code),
                )
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                chunk = json.loads(payload)
                if "error" in chunk:
                    error = chunk["error"]
                    raise ProviderError(str(error), transient=transient_error(error))
                if not started:
                    started = True
                    yield StreamStarted()
                if chunk.get("usage"):
                    usage = usage_from(chunk["usage"])
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    if delta.get("reasoning"):
                        yield ReasoningDelta(delta["reasoning"])
                    if delta.get("content"):
                        text_parts.append(delta["content"])
                        yield TextDelta(delta["content"])
                    if delta.get("tool_calls"):
                        calls.feed(delta["tool_calls"])
                    finish = choice.get("finish_reason") or finish
    except httpx.HTTPError as exc:
        raise ProviderError(f"transport failure talking to {model}: {exc}", transient=True) from exc
    except ValueError as exc:
        raise ProviderError(f"malformed stream from {model}") from exc
    # A reply stopped at the output limit can leave its last tool call half written.
    tool_calls = calls.calls(cut_off=finish == "length")
    message = Message(role="assistant", content="".join(text_parts), tool_calls=tool_calls)
    yield Completion(
        message=message, usage=usage, provider=provider, model=model, finish_reason=finish
    )
