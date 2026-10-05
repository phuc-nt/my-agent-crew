"""What a turn is told of the agent's memory that changes between turns: the summary of the
conversation before this one and the daily notes of yesterday and today.

They used to close the system prompt, where one `memory_save` changed the text in front of
the whole conversation and the provider's cache of everything said so far was lost. They are
now read in front of the message that opens a turn, stored with that message and never
written again: the system prompt is the same from one turn to the next, and the history is a
prefix that only grows.

A message carries only what changed since the conversation was last told: a section in whole
the first time, the lines added to a note that only grew, the new text of one that was
rewritten, and a line saying so for one that is gone. What was told is read back from the
messages themselves, by each section's length and digest, so nothing is told twice and
nothing has to be kept anywhere else. A turn hears of what it saved itself from its own
call; the note reaches the conversation with the next message.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts_turn_notes as words
from my_agent_crew.agents.context import daily_note_sections
from my_agent_crew.clock import day_and_time
from my_agent_crew.llm.types import Message
from my_agent_crew.texts import PREVIOUS_SUMMARY_SECTION_TITLE

if TYPE_CHECKING:
    from my_agent_crew.agent.loop import AgentDeps
    from my_agent_crew.store import Conversation, StoredMessage

WHOLE, ADDED, REPLACED, GONE = "whole", "added", "replaced", "gone"
HEADINGS = {
    WHOLE: words.TURN_NOTES_WHOLE,
    ADDED: words.TURN_NOTES_ADDED,
    REPLACED: words.TURN_NOTES_REPLACED,
    GONE: words.TURN_NOTES_GONE,
}
# The summary is the same section whichever conversation it is of and whenever that one was
# last written to, so it is known by this and not by its title. A note is known by its title.
PREVIOUS = "previous"

Told = Mapping[str, Mapping[str, Any]]


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _entries(raw: str) -> list[dict[str, Any]]:
    try:
        sections = json.loads(raw)["sections"] if raw else []
    except (ValueError, KeyError, TypeError):
        return []
    return [
        entry for entry in sections if isinstance(entry, dict) and entry.get("mode") in HEADINGS
    ]


def _sections(deps: AgentDeps, conv: Conversation | None) -> list[tuple[str, str, str]]:
    """(key, title, body) of everything a turn may be told, the body empty where there is
    nothing: a section that was told and has none now is said to be gone."""
    notes = daily_note_sections(deps.agent, deps.settings.today())
    sections = [(title, title, body) for title, body in notes]
    # A delegated turn is one job with a fresh brief; the summary of some earlier job on
    # the same channel is noise to it. A fork is newest on its channel by rowid, so "the
    # conversation before it" usually is the very one it was cut from — whose summary
    # covers the part after the cut that the fork exists to drop. Neither has the section
    # at all: what a fork's copied messages were told of it stands, and is not called gone.
    if conv is None or conv.parent_call_id or conv.forked_from:
        return sections
    previous = deps.store.previous_for_channel(conv.agent_id, conv.channel, conv.id)
    when = day_and_time(previous.updated_at, deps.settings.zone) if previous else "?"
    summary = previous.summary.strip() if previous else ""
    return [(PREVIOUS, PREVIOUS_SUMMARY_SECTION_TITLE.format(when=when), summary), *sections]


def _change(key: str, title: str, body: str, last: Mapping[str, Any] | None) -> dict | None:
    """How to tell a section given what was last told of it; None when nothing changed."""
    had = int(last["chars"]) if last else 0
    digest = _digest(body)
    if last is None or not had:
        if not body:
            return None
        mode, said = WHOLE, body
    elif not body:
        mode, said, title = GONE, "", str(last["title"])
    elif len(body) == had and digest == last["digest"]:
        return None
    elif len(body) > had and _digest(body[:had]) == last["digest"]:
        mode, said = ADDED, body[had:].strip("\n")
    else:
        mode, said = REPLACED, body
    # The length and digest are of the whole section, which is what the next message is
    # compared with; the body is only what this one says.
    return {
        "key": key,
        "title": title,
        "mode": mode,
        "body": said,
        "chars": len(body),
        "digest": digest,
    }


def told_so_far(raws: Sequence[str]) -> dict[str, dict[str, Any]]:
    """The last thing told of each section, from the notes of a conversation's messages,
    oldest first."""
    return {entry["key"]: entry for raw in raws for entry in _entries(raw)}


def notes_for(deps: AgentDeps, conv_id: str | None, told: Told | None = None) -> str:
    """What a message that opens a turn of the conversation now is stored with, as JSON.
    Never empty: a message with nothing new to tell says so with no sections, which is what
    tells it from one nobody looked at. Without a conversation it is what the first message
    of a new one would carry."""
    conv = deps.store.get(conv_id) if conv_id is not None else None
    if told is None:
        told = told_so_far(deps.store.messages.turn_notes(conv.id)) if conv else {}
    changes = (
        _change(key, title, body, told.get(key)) for key, title, body in _sections(deps, conv)
    )
    return json.dumps({"sections": [c for c in changes if c]}, ensure_ascii=False)


def render(raw: str) -> str:
    """The block the model reads in front of the message; empty when nothing was told."""
    parts = [
        f"{HEADINGS[entry['mode']].format(title=entry['title'])}\n{entry['body']}".rstrip()
        for entry in _entries(raw)
    ]
    if not parts:
        return ""
    return "\n".join((words.TURN_NOTES_OPEN, "\n\n".join(parts), words.TURN_NOTES_CLOSE))


def opening_block(deps: AgentDeps) -> str:
    """What the first message of a new conversation of this agent would be read after."""
    return render(notes_for(deps, None))


def attach_turn_notes(
    deps: AgentDeps,
    conv: Conversation,
    history: Sequence[StoredMessage],
    messages: Sequence[Message],
) -> list[Message]:
    """`messages`, one for each of `history`, each read after what it was stored to tell.
    A conversation none of whose messages was looked at began before messages carried this:
    until its next message is stored with all of it, the turn reads the memory as it is
    now in front of the conversation's first message. A message left unchanged is the same
    object."""
    blocks = [render(stored.turn_notes) for stored in history]
    if not any(stored.turn_notes for stored in history):
        first = next((i for i, s in enumerate(history) if s.message.role == "user"), None)
        if first is not None:
            blocks[first] = render(notes_for(deps, conv.id, told={}))
    return [
        replace(message, content=f"{block}\n\n{message.content}") if block else message
        for block, message in zip(blocks, messages, strict=True)
    ]
