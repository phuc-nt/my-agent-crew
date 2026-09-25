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
class AssistantMessageEvent:
    message_id: int
    content: str
    tool_calls: list[dict[str, Any]]
    provider: str
    model: str
    cost_usd: float | None


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
    reason: str  # "budget" | "max_steps"
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


Event = (
    TextDeltaEvent
    | ThinkingEvent
    | AssistantMessageEvent
    | ToolCallEvent
    | ToolResultEvent
    | ApprovalRequiredEvent
    | DoneEvent
    | HaltedEvent
    | ErrorEvent
    | RouteFallbackEvent
)

_KIND = {
    TextDeltaEvent: "text_delta",
    ThinkingEvent: "thinking",
    AssistantMessageEvent: "assistant_message",
    ToolCallEvent: "tool_call",
    ToolResultEvent: "tool_result",
    ApprovalRequiredEvent: "approval_required",
    DoneEvent: "done",
    HaltedEvent: "halted",
    ErrorEvent: "error",
    RouteFallbackEvent: "route_fallback",
}


def kind_of(event: Event) -> str:
    return _KIND[type(event)]


def to_dict(event: Event) -> dict[str, Any]:
    return {"type": kind_of(event), **asdict(event)}
