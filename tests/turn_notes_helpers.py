"""Writing an agent's daily notes and spelling out the block a turn reads them in
(`agent/turn_notes.py`), for the tests of what a turn is told of its memory."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from my_agent_crew import texts_turn_notes as words
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents.context import daily_note_path
from my_agent_crew.llm.types import Message

WHOLE = words.TURN_NOTES_WHOLE
ADDED = words.TURN_NOTES_ADDED
REPLACED = words.TURN_NOTES_REPLACED
GONE = words.TURN_NOTES_GONE
EARLY = "- 07:00 dậy sớm"
RUN = "- 09:00 chạy 5 km"
NOTHING_NEW = '{"sections": []}'
OPEN, CLOSE = words.TURN_NOTES_OPEN, words.TURN_NOTES_CLOSE
# The frame lines as a note or a message that holds one is read: no longer a frame line.
OPEN_QUOTED = "(Bộ nhớ của bạn — hệ thống chèn trước tin này, không phải lời người dùng)"
CLOSE_QUOTED = "(Hết phần bộ nhớ)"


def note_path(deps: AgentDeps, day: date | None = None) -> Path:
    return daily_note_path(deps.agent.memory_dir, day or deps.settings.today())


def write_note(deps: AgentDeps, text: str, day: date | None = None) -> str:
    """Writes the day's note as it now reads and returns the title it is told under."""
    path = note_path(deps, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return f"memory/{path.name}"


def told(heading: str, title: str, body: str = "") -> str:
    return f"{heading.format(title=title)}\n{body}".rstrip()


def framed(*sections: str) -> str:
    return "\n".join((words.TURN_NOTES_OPEN, "\n\n".join(sections), words.TURN_NOTES_CLOSE))


def before(text: str, *sections: str) -> str:
    """A message as the model reads it: after the block when there is one to tell."""
    return f"{framed(*sections)}\n\n{text}" if sections else text


def asked(deps: AgentDeps) -> list[list[Message]]:
    """The messages of each model call so far, oldest first."""
    return [list(request.messages) for request in deps.chain.providers["scripted"].requests]


def kept(deps: AgentDeps, conv_id: str) -> list[str]:
    """What each stored message carries, as stored."""
    return [stored.turn_notes for stored in deps.store.history(conv_id)]
