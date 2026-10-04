"""Offline providers. `ScriptedProvider` replays canned completions for tests;
`EchoProvider` is a product feature (`MY_AGENT_ROUTES=fake:echo`) so the UI, e2e
tests and a first run all work without any API key. Both stream an answer the way a
model does: its words, then the arguments of each tool call, a piece at a time. On
`fake:slow` the echo waits between two pieces, so the stream can be watched arriving."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, replace

from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.llm.types import (
    Completion,
    Message,
    StreamItem,
    TextDelta,
    ToolCall,
    ToolCallDelta,
    ToolSpec,
    Usage,
)

_TOOL_DIRECTIVE = re.compile(r"^/tool\s+(\w+)\s*(\{.*\})?\s*$", re.DOTALL)
_TOOL_LINE = re.compile(r"^/tool\b", re.MULTILINE)
# The wait between two pieces on the `slow` model: long enough to watch an answer arrive.
SLOW_MODEL, SLOW_CHUNK_S = "slow", 0.1


def _chunked(text: str, size: int = 12) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def _pieces(text: str, calls: Sequence[ToolCall]) -> list[StreamItem]:
    """An answer as a stream sends it ahead of the completion: the words, then each call's
    arguments under the call's place in the answer. An answer with no words sends none."""
    pieces: list[StreamItem] = [TextDelta(piece) for piece in _chunked(text)]
    for index, call in enumerate(calls):
        arguments = json.dumps(call.arguments, ensure_ascii=False)
        pieces += [ToolCallDelta(index, call.name, piece) for piece in _chunked(arguments)]
    return pieces


@dataclass(frozen=True)
class Request:
    """What the scripted provider was asked, kept so tests can assert on it."""

    messages: tuple[Message, ...]
    tools: tuple[ToolSpec, ...]
    model: str
    reasoning: str = ""


class ScriptedProvider:
    """Yields the given completions in order; raising entries simulate upstream failure."""

    name = "scripted"

    def __init__(self, script: Sequence[Completion | ProviderError], name: str = "scripted"):
        self.name = name
        self._script = list(script)
        self.requests: list[Request] = []

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        model: str,
        reasoning: str = "",
    ) -> AsyncIterator[StreamItem]:
        self.requests.append(Request(tuple(messages), tuple(tools), model, reasoning))
        if not self._script:
            raise ProviderError("script exhausted")
        item = self._script.pop(0)
        if isinstance(item, ProviderError):
            raise item
        for piece in _pieces(item.message.content, item.message.tool_calls):
            yield piece
        yield replace(item, provider=self.name, model=model)


def completion(
    content: str = "",
    tool_calls: Sequence[ToolCall] = (),
    cost_usd: float | None = 0.001,
    model: str = "scripted-model",
) -> Completion:
    return Completion(
        message=Message(role="assistant", content=content, tool_calls=tuple(tool_calls)),
        usage=Usage(prompt_tokens=10, completion_tokens=5, cost_usd=cost_usd),
        provider="scripted",
        model=model,
    )


class EchoProvider:
    """Answers with the user's last message. A message that ends in `/tool <name> {json}`
    from a line of its own becomes a tool call, whatever comes above it (the canvas note the
    prompt puts first, say), so every tool path can be walked by hand. `sleep` is what the
    `slow` model waits with; every other model never waits."""

    name = "fake"

    def __init__(self, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self._sleep = sleep

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSpec],
        model: str,
        reasoning: str = "",
    ) -> AsyncIterator[StreamItem]:
        last = messages[-1]
        if last.role == "tool":
            text = f"Kết quả công cụ {last.name}:\n{last.content[:400]}"
            calls: tuple[ToolCall, ...] = ()
        else:
            call_id = f"call_echo_{len(messages)}_{uuid.uuid4().hex[:8]}"
            text, calls = _interpret(last.content, tools, call_id)
        for position, piece in enumerate(_pieces(text, calls)):
            if position and model == SLOW_MODEL:
                await self._sleep(SLOW_CHUNK_S)
            yield piece
        yield Completion(
            message=Message(role="assistant", content=text, tool_calls=calls),
            usage=Usage(
                prompt_tokens=len(last.content) // 4, completion_tokens=len(text) // 4, cost_usd=0.0
            ),
            provider=self.name,
            model=model,
        )


def _interpret(
    text: str, tools: Sequence[ToolSpec], call_id: str
) -> tuple[str, tuple[ToolCall, ...]]:
    stripped = text.strip()
    starts = [line.start() for line in _TOOL_LINE.finditer(stripped)]
    match = _TOOL_DIRECTIVE.match(stripped[starts[-1] :]) if starts else None
    if not match:
        return f"(echo) {text}", ()
    name, raw_args = match.group(1), match.group(2) or "{}"
    if name not in {t.name for t in tools}:
        return f"Không có công cụ tên {name}.", ()
    try:
        args = json.loads(raw_args)
    except ValueError:
        return "Tham số công cụ phải là JSON.", ()
    return "", (ToolCall(id=call_id, name=name, arguments=args),)
