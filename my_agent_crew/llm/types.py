"""Provider-neutral chat types. Providers translate to and from their wire format."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Message:
    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    name: str | None = None
    # Pictures shown with the text, as data URLs. Only a vision route ever gets them;
    # they are not written to the store.
    images: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    # None means the upstream did not report a price; it is never guessed.
    cost_usd: float | None = None
    # The part of completion_tokens the model spent thinking; None when not reported.
    reasoning_tokens: int | None = None
    # The part of prompt_tokens served from the provider's prompt cache; None when not
    # reported. What tells a cheap turn from one that re-read the whole history.
    cached_tokens: int | None = None


@dataclass(frozen=True)
class Completion:
    message: Message
    usage: Usage
    provider: str
    model: str
    finish_reason: str = "stop"


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ReasoningDelta:
    """A piece of the model's thinking. Never shown or stored: it only tells the person
    the model is working before its first word arrives."""

    text: str


@dataclass(frozen=True)
class StreamStarted:
    """The first chunk of a streamed completion arrived. It carries nothing itself: it
    marks the time to first token, which for a tool-only answer no delta would."""


@dataclass(frozen=True)
class RouteFailed:
    """A route gave up before its first token and the chain moved on to the next one."""

    provider: str
    model: str
    error: str


StreamItem = TextDelta | ReasoningDelta | StreamStarted | Completion | RouteFailed
