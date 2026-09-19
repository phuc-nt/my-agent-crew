"""Events a turn emits. The SSE layer serialises them one-to-one; the UI renders them."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TextDeltaEvent:
    text: str


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


@dataclass(frozen=True)
class ApprovalRequiredEvent:
    approval_id: str
    tool_call_id: str
    name: str
    arguments: dict[str, Any]


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
