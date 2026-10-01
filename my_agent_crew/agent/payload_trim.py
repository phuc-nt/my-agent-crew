"""What a turn's prompt carries of the conversation's canvases: none of the documents earlier
turns sent to a canvas, and each person's message read after the canvas note it was stored
with.

A canvas write carries the whole text it saves: a create's or a rewrite's `content`, an
edit's `old` and `new`. Sent again with every later turn, a few drafts would fill the prompt
with text the canvas already holds. Once the turn that wrote it is over, that text becomes a
note of where it went: the canvas and version its result named, to be read back with
`artifact_read`; that the write failed and saved nothing; or that it was cut off mid-call,
so whether it saved is unknown and the canvas should be looked at before writing again.

The turn that wrote it keeps every word to its end. A steer, the loop guard's redirect and a
child's wrap-up note are all messages from the user's side, so "before the last user
message" would move mid-turn; the boundary is where the turn's run began instead, which a
turn resumed after an approval keeps. Only the prompt changes: the store keeps every call
as it was made.

A canvas note tells what the canvases were when its message came, so only the turn that
message opened reads it whole; an earlier turn's note is read as a fixed stub, which changes
the prompt once, when that turn is over, and keeps the history a stable prefix after that."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

from my_agent_crew.agent.context_trim import MIN_TRIM_CHARS
from my_agent_crew.artifacts.tag import TAG_RE
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.store.runs import RUNNING
from my_agent_crew.texts_canvas import (
    CANVAS_NOTE_STUB,
    CANVAS_PAYLOAD_CUT_OFF,
    CANVAS_PAYLOAD_FAILED,
    CANVAS_PAYLOAD_SAVED,
)
from my_agent_crew.texts_queue import INTERRUPTED_TOOL

if TYPE_CHECKING:
    from my_agent_crew.store import Store, StoredMessage

# The arguments of each canvas write (`tools/artifact.py`) that carry document text.
CANVAS_PAYLOADS = {
    "artifact_create": ("content",),
    "artifact_rewrite": ("content",),
    "artifact_edit": ("old", "new"),
}


def turn_boundary(store: Store, conv_id: str) -> int:
    """The last message written before this turn began: where the conversation's running
    run started, set before the person's message and kept when a paused turn resumes, or
    the newest message when no run is under way (a turn not tracked as a run)."""
    run = store.runs.latest_for_conversation(conv_id)
    if run is not None and run.status == RUNNING and run.after_seq is not None:
        return run.after_seq
    return store.messages.max_seq(conv_id)


def trim_canvas_payloads(history: Sequence[StoredMessage], turn_start: int | None) -> list[Message]:
    """The messages of `history`, with the canvas writes made by `turn_start` carrying a note
    in place of each long document text. A message left unchanged is the same object."""
    messages = [stored.message for stored in history]
    if turn_start is None:
        return messages
    results = _results(history)
    out: list[Message] = []
    for index, (stored, message) in enumerate(zip(history, messages, strict=True)):
        if stored.seq > turn_start or not message.tool_calls:
            out.append(message)
            continue
        calls = tuple(_trimmed(call, results.get((index, call.id))) for call in message.tool_calls)
        changed = any(new is not old for new, old in zip(calls, message.tool_calls, strict=True))
        out.append(replace(message, tool_calls=calls) if changed else message)
    return out


def attach_canvas_notes(
    history: Sequence[StoredMessage], messages: Sequence[Message], turn_start: int | None
) -> list[Message]:
    """`messages`, one for each of `history`, with every message stored with a canvas note
    read after that note, or after the stub when the note is older than this turn. The queue
    writes a message just before the run of the turn that answers it begins, so the turn
    starts at that message, not after it. A message left unchanged is the same object."""
    out: list[Message] = []
    for stored, message in zip(history, messages, strict=True):
        if not stored.context:
            out.append(message)
            continue
        current = turn_start is None or stored.seq >= turn_start
        note = stored.context if current else CANVAS_NOTE_STUB
        out.append(replace(message, content=f"{note}\n\n{message.content}"))
    return out


def _results(history: Sequence[StoredMessage]) -> dict[tuple[int, str], str]:
    """The result of each call, keyed by the index of the message that made it and its id. A
    model may reuse an id, so a result answers the latest call made under it."""
    made: dict[str, int] = {}
    results: dict[tuple[int, str], str] = {}
    for index, stored in enumerate(history):
        message = stored.message
        if message.role == "assistant":
            made.update((call.id, index) for call in message.tool_calls)
        elif message.role == "tool" and message.tool_call_id in made:
            call_id = message.tool_call_id
            results[(made.pop(call_id), call_id)] = message.content
    return results


def _trimmed(call: ToolCall, result: str | None) -> ToolCall:
    """A call with no result yet is passed on whole: what became of its text is unknown."""
    payloads = CANVAS_PAYLOADS.get(call.name, ())
    if result is None or not payloads:
        return call
    arguments = dict(call.arguments)
    for name in payloads:
        value = arguments.get(name)
        if isinstance(value, str) and len(value) > MIN_TRIM_CHARS:
            arguments[name] = _note(result, len(value))
    return call if arguments == call.arguments else replace(call, arguments=arguments)


def _note(result: str, chars: int) -> str:
    """Only a write that saved opens its result with the canvas tag (`artifacts/tag.py`). A
    call the turn left unanswered is closed as interrupted (`close_interrupted`) when the
    next message comes: it may have run, so the note must not say nothing was saved."""
    tag = TAG_RE.match(result)
    if tag is not None:
        return CANVAS_PAYLOAD_SAVED.format(chars=chars, id=tag[1], version=tag[2])
    if result == INTERRUPTED_TOOL:
        return CANVAS_PAYLOAD_CUT_OFF.format(chars=chars)
    return CANVAS_PAYLOAD_FAILED.format(chars=chars)
