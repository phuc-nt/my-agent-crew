"""Events a turn emits. The SSE layer serialises them one-to-one; the UI renders them."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TextDeltaEvent:
    text: str


@dataclass(frozen=True)
class ThinkingEvent:
    """The model started thinking before it answers. Sent once per model call, without the
    thoughts themselves, so a slow first word does not look like a hung turn."""


@dataclass(frozen=True)
class ModelCallEvent:
    """Where a model call stands: "sent" when the request leaves, "first_token" when the
    first chunk of any kind arrives. Without it a call that answers only with tool calls
    has no first word to time, and its step would read as taking no time at all."""

    stage: str


@dataclass(frozen=True)
class AssistantMessageEvent:
    message_id: int
    content: str
    tool_calls: list[dict[str, Any]]
    # Both None when no model spoke: the reply was handed on whole from a delegated child.
    provider: str | None
    model: str | None
    cost_usd: float | None
    prompt_tokens: int | None = None
    cached_tokens: int | None = None


@dataclass(frozen=True)
class ToolCallEvent:
    tool_call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResultEvent:
    tool_call_id: str
    name: str
    ok: bool
    output: str
    # How the output was brought under the cap ("none", "json" or "cut") and how long it
    # was first. Carried so a run card can say the model answered from a shortened output.
    shaped_kind: str = "none"
    original_chars: int = 0
    # What the tool paid a model (a picture, a scanned page, a long output summarised),
    # when `metered`; None there means the provider gave no price. The run adds it up.
    cost_usd: float | None = None
    metered: bool = False


@dataclass(frozen=True)
class ApprovalRequiredEvent:
    approval_id: str
    tool_call_id: str
    name: str
    arguments: dict[str, Any]
    # Why this call is waiting although the conversation is autonomous; empty otherwise.
    reason: str = ""
    # When an unanswered request closes as expired (ISO, UTC); empty for legacy rows.
    expires_at: str = ""
    # "tool" when a call is waiting to be authorised, "question" when the agent is asking
    # the person something. The UI shows a different card for each.
    kind: str = "tool"
    # The choices a question offered, if it offered any. Never set for a tool.
    options: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DoneEvent:
    spent_usd: float
    unknown_cost_calls: int


@dataclass(frozen=True)
class HaltedEvent:
    reason: str  # "budget" | "max_steps" | "loop" (the same tool calls over and over)
    spent_usd: float


@dataclass(frozen=True)
class ErrorEvent:
    message: str


@dataclass(frozen=True)
class RouteFallbackEvent:
    """One route failed before answering and the next one is being tried."""

    provider: str
    model: str
    error: str


@dataclass(frozen=True)
class QueuedEvent:
    """The message waits instead of starting a turn, because one is running: a follow-up
    runs once that turn ends, a steer is read by it before its next model call."""

    item_id: int
    kind: str  # "follow_up" | "steer"
    position: int  # its place in line, 1 for the first


@dataclass(frozen=True)
class SteerEvent:
    """Messages sent while the turn ran were handed to it before its next model call."""

    text: str
    count: int


@dataclass(frozen=True)
class UserContextEvent:
    """The canvas note stored with the message this turn answers. The web drew that message's
    bubble before the server had stored anything, so the note reaches it here, on the stream
    of the tab that sent the message. It names no message: the bubble is that tab's latest."""

    context: str


@dataclass(frozen=True)
class ToolCallDeltaEvent:
    """Arguments of a canvas write as the model streams them, sent only to the request that
    streams the turn. `attempt` counts the route attempts this model call gave up, from 0;
    an empty `name` calls an attempt off, and whoever drew its pieces drops them."""

    index: int
    name: str
    chunk: str
    attempt: int


Event = (
    TextDeltaEvent
    | ThinkingEvent
    | ModelCallEvent
    | AssistantMessageEvent
    | ToolCallEvent
    | ToolResultEvent
    | ApprovalRequiredEvent
    | DoneEvent
    | HaltedEvent
    | ErrorEvent
    | RouteFallbackEvent
    | QueuedEvent
    | SteerEvent
    | UserContextEvent
    | ToolCallDeltaEvent
)

# Events that flow through a turn but are not worth a write or a broadcast on their own: the
# run they belong to is stored and sent at the next step boundary. The canvas note and the
# pieces of a canvas write also quote a canvas, so only their own stream may carry them.
STREAMING_EVENTS = (
    TextDeltaEvent,
    ThinkingEvent,
    ModelCallEvent,
    UserContextEvent,
    ToolCallDeltaEvent,
)

_KIND = {
    TextDeltaEvent: "text_delta",
    ThinkingEvent: "thinking",
    ModelCallEvent: "model_call",
    AssistantMessageEvent: "assistant_message",
    ToolCallEvent: "tool_call",
    ToolResultEvent: "tool_result",
    ApprovalRequiredEvent: "approval_required",
    DoneEvent: "done",
    HaltedEvent: "halted",
    ErrorEvent: "error",
    RouteFallbackEvent: "route_fallback",
    QueuedEvent: "queued",
    SteerEvent: "steer",
    UserContextEvent: "user_context",
    ToolCallDeltaEvent: "tool_call_delta",
}


def kind_of(event: Event) -> str:
    return _KIND[type(event)]


def to_dict(event: Event) -> dict[str, Any]:
    return {"type": kind_of(event), **asdict(event)}
