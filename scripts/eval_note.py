"""Whether what the person did on a canvas reached the agent, in every run with canvas steps.

The agent hears of a canvas step only through the canvas note the server stores with the
person's next message (`store/canvas_note.py`). So the message holding each text a case sent
must have a note telling of every canvas the person made or saved since the text before, at the
version they left it, in one of the forms a note tells a change in, and quoting the passage the
message carried as the note quotes it. A line naming the canvas open in the panel is not enough.
A note that falls short fails the run: the case's expectations would judge an agent that never
heard of the step.

A case whose changes outgrow the note's size cap fails here, and so does one that saves a canvas
back to what the agent last heard of before its next message: the note has nothing to tell."""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from eval_canvas import NoteDue
from eval_check import RUN, Failure
from eval_observe import turn_numbers

from my_agent_crew.store.canvas_quote import quoted, shown
from my_agent_crew.texts_canvas import (
    CANVAS_NOTE_BUMP,
    CANVAS_NOTE_EDITED,
    CANVAS_NOTE_LARGE,
    CANVAS_NOTE_NEW,
)

CHANGE_FORMS = (CANVAS_NOTE_NEW, CANVAS_NOTE_EDITED, CANVAS_NOTE_BUMP, CANVAS_NOTE_LARGE)


def note_failures(
    messages: Sequence[Mapping[str, Any]], sent: Sequence[str], due: Sequence[NoteDue]
) -> Iterator[Failure]:
    """A failure for each canvas and each passage that the note of the message owing it does
    not tell of; `due` holds what each text in `sent` owes. A text the conversation does not
    hold is `observe`'s to report."""
    numbers = turn_numbers(messages, sent)
    for number, owed in enumerate(due, 1):
        held = next((m for m, n in zip(messages, numbers, strict=True) if n == number), None)
        if held is None:
            continue
        note = str(held.get("context") or "")
        for artifact_id, version in owed.saved.items():
            if not _tells(note, artifact_id, version):
                detail = f"does not tell of {artifact_id} at v{version}"
                yield Failure(RUN, f"the canvas note of message {number} {detail}")
        if owed.passage and quoted(shown(owed.passage)) not in note:
            detail = "does not quote the passage it carried"
            yield Failure(RUN, f"the canvas note of message {number} {detail}")


def _tells(note: str, artifact_id: str, version: int) -> bool:
    """Whether a line of the note opens what it says of this canvas at `version`."""
    forms = []
    for form in CHANGE_FORMS:
        line = form.format(title="\0", id=artifact_id, base="\1", head=version)
        forms.append(re.escape(line).replace("\0", "[^»]*").replace("\1", r"\d+"))
    opens = re.compile("|".join(forms))
    return any(opens.match(line) for line in note.splitlines())
