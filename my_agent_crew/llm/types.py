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
    # Why the arguments the model sent were not a JSON object, "" when they were. Such a
    # call carries `{}` and is answered with this reason instead of being run. Never sent
    # back to a provider: the wire carries only id, name and arguments.
    invalid: str = ""

    def to_dict(self) -> dict[str, Any]:
        """As stored and served. `invalid` appears only when set, so every ordinary call
        keeps the shape it always had and a server rolled back past this field still
        reads it."""
        row: dict[str, Any] = {"id": self.id, "name": self.name, "arguments": self.arguments}
        if self.invalid:
            row["invalid"] = self.invalid
        return row


@dataclass(frozen=True)
class AudioPart:
    """One audio clip attached to a message, ready for the wire. `data` is base64 ASCII,
    `format` the OpenRouter-recognised extension (`"ogg"`, `"mp3"`, …)."""

    data: str
    format: str


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
    # Audio shown with the text. Only an audio route ever gets it; it is not written to
    # the store.
    audio: tuple[AudioPart, ...] = ()


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
class ToolCallDelta:
    """One piece of the arguments of a tool call the model is still writing. `index` is the
    call's position among the calls of the answer, counted from 0 whatever number the
    provider gave it: the place the finished call has in the `Completion`'s `tool_calls`.
    `name` is the call's name as assembled so far, empty while a stream that sends
    arguments ahead of the name has not said it yet. The whole call still arrives in the
    `Completion`: a piece is for following along, never for running."""

    index: int
    name: str
    chunk: str


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


@dataclass(frozen=True)
class RouteRetry:
    """A route hit a passing upstream failure before any text was shown, and the chain is
    asking the same route again. Whatever the failed attempt streamed (timing, thinking)
    is superseded by the new attempt."""

    provider: str
    model: str
    error: str


StreamItem = (
    TextDelta
    | ReasoningDelta
    | ToolCallDelta
    | StreamStarted
    | Completion
    | RouteFailed
    | RouteRetry
)
