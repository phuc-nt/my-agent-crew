"""The engine's messages and tools in the shape the Claude Messages API takes.

The differences from the OpenAI-compatible shape: the system prompt is a top-level
field, not a message; a tool call is a `tool_use` content block of the assistant
message; its result is a `tool_result` block of the next user message, and results come
before anything else in that message; roles must alternate. Thinking blocks are never
sent back: the engine keeps no thinking, and a history without any is always valid.

Three cache breakpoints mark what each request shares with the next: the end of the
tools, the end of the system prompt and the end of the conversation. The API renders
tools, then system, then messages, so each breakpoint caches everything before it.
The first two may be kept for an hour (`stable_ttl`); the conversation's end, which moves
with every request, always keeps the default five minutes, so the longer lifetimes come
first as the API requires.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.llm.types import Message, ToolSpec

CACHE = {"type": "ephemeral"}
DEFAULT_TTL = "5m"
# Said in place of a result the history never recorded (a turn cut off between a call
# and its answer): the API refuses a tool call left without a result.
NO_RESULT = "no result was recorded for this call"
# Opens the first message when a history starts with the assistant.
CONTINUED = "(continued)"
# Families that take `output_config.effort`. Others (Claude Haiku 4.5, Claude Sonnet
# 4.5 and older) reject it, so an unknown model is sent none rather than a 400.
EFFORT_FAMILIES = (
    "claude-fable-",
    "claude-mythos-",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
    "claude-haiku-5",
)
# The engine's efforts are OpenRouter's; the Claude API has no `minimal`.
EFFORTS = {"minimal": "low", "low": "low", "medium": "medium", "high": "high"}


def tool_id(raw: str | None) -> str:
    """An id the API accepts (`[A-Za-z0-9_-]+`). Ids written by other providers, kept in
    the history, can carry dots or colons; the same id maps to the same text on both the
    call and its result, so the pair still matches."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", raw or "") or "call"


def _image(url: str) -> dict[str, Any]:
    if url.startswith("data:"):
        header, _, data = url.partition(",")
        media = header[5:].split(";")[0] or "image/png"
        return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}
    return {"type": "image", "source": {"type": "url", "url": url}}


def _text(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": text}] if text.strip() else []


def _blocks(m: Message) -> list[dict[str, Any]]:
    if m.audio:
        raise ProviderError("the Claude API takes no audio input")
    pictures = [_image(url) for url in m.images]
    if m.role == "tool":
        block: dict[str, Any] = {"type": "tool_result", "tool_use_id": tool_id(m.tool_call_id)}
        content = pictures + _text(m.content)
        if content:
            block["content"] = content if pictures else m.content
        return [block]
    blocks = pictures + _text(m.content)
    if m.role == "assistant":
        blocks += [
            {"type": "tool_use", "id": tool_id(c.id), "name": c.name, "input": c.arguments}
            for c in m.tool_calls
        ]
    return blocks


def _merged(messages: Sequence[Message]) -> list[dict[str, Any]]:
    """Alternating user/assistant messages. A tool result is user content, and a system
    message after the first non-system one becomes user text."""
    out: list[dict[str, Any]] = []
    for m in messages:
        role = "assistant" if m.role == "assistant" else "user"
        blocks = _blocks(m)
        if not blocks:
            continue
        if out and out[-1]["role"] == role:
            out[-1]["content"] += blocks
        else:
            out.append({"role": role, "content": blocks})
    return out


def _paired(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every tool call answered in the next message, results first, and no result left
    without its call (that one is kept as plain text, so nothing the tool said is lost)."""
    for i, m in enumerate(messages):
        if m["role"] != "user":
            continue
        before = messages[i - 1]["content"] if i else []
        asked = [b["id"] for b in before if b["type"] == "tool_use"]
        results, rest = [], []
        for b in m["content"]:
            if b["type"] != "tool_result":
                rest.append(b)
            elif b["tool_use_id"] in asked:
                results.append(b)
            else:
                rest.append({"type": "text", "text": f"Tool result: {b.get('content', '')}"})
        answered = {b["tool_use_id"] for b in results}
        results += [
            {"type": "tool_result", "tool_use_id": a, "content": NO_RESULT, "is_error": True}
            for a in asked
            if a not in answered
        ]
        m["content"] = results + rest
    if messages and any(b["type"] == "tool_use" for b in messages[-1]["content"]):
        messages.append({"role": "user", "content": []})
        return _paired(messages)
    if messages and messages[0]["role"] == "assistant":
        messages.insert(0, {"role": "user", "content": [{"type": "text", "text": CONTINUED}]})
    return messages


def cache_mark(ttl: str = DEFAULT_TTL) -> dict[str, str]:
    return CACHE if ttl == DEFAULT_TTL else {**CACHE, "ttl": ttl}


def to_wire(
    messages: Sequence[Message], stable_ttl: str = DEFAULT_TTL
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`(system, messages)`: the leading system messages as system text blocks, the rest
    as alternating messages, with the last block of each list marked for the cache."""
    lead = 0
    while lead < len(messages) and messages[lead].role == "system":
        lead += 1
    system = [b for m in messages[:lead] for b in _text(m.content)]
    wire = _paired(_merged(messages[lead:]))
    for blocks, mark in (
        (system, cache_mark(stable_ttl)),
        (wire[-1]["content"] if wire else [], CACHE),
    ):
        if blocks:
            blocks[-1]["cache_control"] = mark
    return system, wire


def tools_to_wire(tools: Sequence[ToolSpec], ttl: str = DEFAULT_TTL) -> list[dict[str, Any]]:
    out = [
        {"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools
    ]
    if out:
        out[-1]["cache_control"] = cache_mark(ttl)
    return out


def effort_for(model: str, reasoning: str) -> str | None:
    """The `output_config.effort` to send, or None to leave the model's default."""
    if not reasoning or not model.startswith(EFFORT_FAMILIES):
        return None
    return EFFORTS.get(reasoning)


def request_body(
    messages: Sequence[Message],
    tools: Sequence[ToolSpec],
    model: str,
    reasoning: str,
    max_tokens: int,
    stable_ttl: str = DEFAULT_TTL,
) -> dict[str, Any]:
    system, wire = to_wire(messages, stable_ttl)
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": wire,
        "stream": True,
    }
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools_to_wire(tools, stable_ttl)
    effort = effort_for(model, reasoning)
    if effort:
        body["output_config"] = {"effort": effort}
    return body
