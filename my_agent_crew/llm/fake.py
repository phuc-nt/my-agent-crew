"""Offline providers. `ScriptedProvider` replays canned completions for tests;
`EchoProvider` is a product feature (`MY_AGENT_ROUTES=fake:echo`) so the UI, e2e
tests and a first run all work without any API key."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, replace

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

_TOOL_DIRECTIVE = re.compile(r"^/tool\s+(\w+)\s*(\{.*\})?\s*$", re.DOTALL)


def _chunked(text: str, size: int = 12) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


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
        for piece in _chunked(item.message.content):
            if piece:
                yield TextDelta(piece)
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
    """Answers with the user's last message. A message of the form
    `/tool <name> {json}` becomes a tool call, so every tool path can be walked by hand."""

    name = "fake"

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
            call_id = f"call_echo_{len(messages)}"
            text, calls = _interpret(last.content, tools, call_id)
        for piece in _chunked(text):
            yield TextDelta(piece)
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
    match = _TOOL_DIRECTIVE.match(text.strip())
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
