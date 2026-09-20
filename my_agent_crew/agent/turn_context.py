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
PRESENT_SOURCES = (CHAT, TELEGRAM)

_turn_source: ContextVar[str] = ContextVar("turn_source", default=CHAT)


def set_turn_source(source: str) -> None:
    _turn_source.set(normalize_source(source))


def turn_source() -> str:
    return _turn_source.get()


def normalize_source(source: str) -> str:
    """Run sources name the schedule they came from (`job:coach/brief`); memory only
    cares that it was a job."""
    return JOB if source.startswith(f"{JOB}:") else source


def conversation_source(store: Store, conv_id: str) -> str:
    """Where this conversation's work came from, so a turn resumed after an approval is
    judged the same way as the turn that asked for it."""
    run = store.runs.latest_for_conversation(conv_id)
    return normalize_source(run.source) if run is not None else CHAT


def person_is_present() -> bool:
    """True when someone is at the other end to notice what the agent remembers."""
    return turn_source() in PRESENT_SOURCES
