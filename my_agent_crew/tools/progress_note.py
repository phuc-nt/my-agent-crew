"""A line the agent writes about what it is doing, for whoever is watching.

A long run is opaque from outside. The timeline shows which tools were called, but a tool
name says what was used, not what it was for: five `shell_run` rows in sequence tell the
person nothing about whether the agent is on track or lost. A note is the agent saying so
in its own words.

Two things follow from that purpose and shape the whole tool.

It never pauses. A note that needed approval would arrive after the thing it describes was
already decided, which is the opposite of watching work happen. So `requires_approval` is
False and nothing here consults the approval machinery.

It is not a tool call in the timeline. The step it produces has its own kind, because a
note has no duration worth reading and cannot fail: rendering it as a tool row would put a
stopwatch and a success mark on a sentence. See `activity/steps.py`.

The note is not memory. It lives on the run and is gone when the run scrolls away; a fact
worth keeping belongs in the agent's notes, and the description says so, because a model
given a free-form writing tool will otherwise use it as one.
"""

from __future__ import annotations

from typing import Any

from my_agent_crew.tools.progress_note_texts import (
    PROGRESS_NOTE_DESCRIPTION,
    PROGRESS_NOTE_EMPTY,
    PROGRESS_NOTE_OK,
)
from my_agent_crew.tools.registry import Tool

PROGRESS_NOTE_TOOL_NAME = "progress_note"

#: Long enough for a sentence about the work, short enough to stay one timeline row. A
#: model handed a larger budget writes a paragraph, and a paragraph in a progress strip is
#: no longer glanceable — which was the only reason for the tool.
MAX_NOTE_CHARS = 200

PROGRESS_NOTE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": (
                "Bạn đang làm gì, một câu ngắn, bằng ngôn ngữ người dùng đang dùng."
                f" Tối đa {MAX_NOTE_CHARS} ký tự, phần thừa sẽ bị cắt."
            ),
        },
    },
    "required": ["text"],
}


def note_text(arguments: dict[str, Any]) -> str:
    """The note as it will be shown: collapsed to one line and cut to the budget.

    Cutting is deliberate rather than an error. A note is a courtesy to the reader, so a
    model that writes too much should still have its turn continue with the note shortened
    — failing the call would turn a formatting slip into a broken run.
    """
    text = " ".join(str(arguments.get("text", "")).split())
    return text[:MAX_NOTE_CHARS]


async def _run(arguments: dict[str, Any]) -> str:
    """The note reaches the timeline from the tool call itself, not from this result.

    The step is written when the call is seen, so it shows while the work it describes is
    still happening. By the time a result exists the note would be old news, so all this
    returns is an acknowledgement.
    """
    return PROGRESS_NOTE_OK if note_text(arguments) else PROGRESS_NOTE_EMPTY


def build_progress_note_tool() -> Tool:
    return Tool(
        PROGRESS_NOTE_TOOL_NAME,
        PROGRESS_NOTE_DESCRIPTION,
        PROGRESS_NOTE_SCHEMA,
        _run,
        requires_approval=False,
    )
