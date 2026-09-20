"""Keeping a long turn's prompt from filling up with old tool output.

A work agent runs a hundred steps; the file it read at step three is usually dead weight
by step ninety, but it is still sent on every request. Only the prompt is trimmed — the
store keeps every message in full, so the transcript and the UI are unaffected."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from my_agent_crew import texts
from my_agent_crew.llm.types import Message

# How many of the most recent tool results stay in full. Enough to cover one read-edit-test
# cycle, which is what the model actually reasons over.
KEEP_TOOL_OUTPUTS = 20
# Short results cost less than the note explaining they were dropped.
MIN_TRIM_CHARS = 200


def trim_tool_outputs(messages: Sequence[Message], keep: int = KEEP_TOOL_OUTPUTS) -> list[Message]:
    """The same messages, with tool results older than the last `keep` replaced by a
    one-line stub naming their size so the model can fetch them again if it needs to."""
    indexes = [i for i, m in enumerate(messages) if m.role == "tool"]
    if len(indexes) <= keep:
        return list(messages)
    stale = set(indexes[: len(indexes) - keep])
    out: list[Message] = []
    for index, message in enumerate(messages):
        if index in stale and len(message.content) > MIN_TRIM_CHARS:
            stub = texts.TOOL_OUTPUT_TRIMMED.format(chars=len(message.content))
            out.append(replace(message, content=stub))
        else:
            out.append(message)
    return out
