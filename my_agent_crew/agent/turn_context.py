"""Where the turn being run came from, readable by a tool deep inside it.

A tool decides whether it may write straight to the person's memory or must propose the
write instead, and that depends on whether the person is there to see it. Passing the
source down through every tool signature would touch code that does not care, so it
travels in a context variable that `run_turn` sets for the turn.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # the store imports nothing from the agent package
    from my_agent_crew.store import Store

CHAT, TELEGRAM, JOB, WEB = "chat", "telegram", "job", "web"
# A turn another agent asked for; the rest of the source names the parent conversation.
DELEGATE = "delegate"
PRESENT_SOURCES = (CHAT, TELEGRAM)

_turn_source: ContextVar[str] = ContextVar("turn_source", default=CHAT)
_turn_conversation_id: ContextVar[str] = ContextVar("turn_conversation_id", default="")
_turn_depth: ContextVar[int] = ContextVar("turn_depth", default=0)
_tool_call_id: ContextVar[str] = ContextVar("tool_call_id", default="")


def set_turn_source(source: str) -> None:
    _turn_source.set(normalize_source(source))


def turn_source() -> str:
    return _turn_source.get()


def set_turn_conversation(conv_id: str, depth: int = 0) -> None:
    """Which conversation this turn belongs to and how far it is from the person. A tool
    that opens a conversation of its own needs both, and neither belongs in its arguments."""
    _turn_conversation_id.set(conv_id)
    _turn_depth.set(depth)


def turn_conversation_id() -> str:
    return _turn_conversation_id.get()


def turn_depth() -> int:
    return _turn_depth.get()


def set_tool_call_id(call_id: str) -> None:
    """The id of the call being carried out right now. A tool with a side effect outside
    the store — opening a conversation, say — uses it to recognise its own earlier attempt
    after an interruption, instead of doing the thing twice. It is deliberately not a tool
    argument: the model must not be able to name it."""
    _tool_call_id.set(call_id)


def tool_call_id() -> str:
    return _tool_call_id.get()


def normalize_source(source: str) -> str:
    """Run sources name what they came from (`job:coach/brief`, `delegate:<conv>`); the
    rest of the code only cares which kind it was."""
    for prefix in (JOB, DELEGATE):
        if source.startswith(f"{prefix}:"):
            return prefix
    return source


def conversation_source(store: Store, conv_id: str) -> str:
    """Where this conversation's work came from, so a turn resumed after an approval is
    judged the same way as the turn that asked for it."""
    run = store.runs.latest_for_conversation(conv_id)
    return normalize_source(run.source) if run is not None else CHAT


def person_is_present() -> bool:
    """True when someone is at the other end to notice what the agent remembers."""
    return turn_source() in PRESENT_SOURCES
