"""What a delegated run that did not finish had already done.

A child that stops at its step cap, on an error or on an interruption hands back its last
words, which are often half a thought ("that table does not exist…"). Read alone they say
nothing happened, and the delegator hands the same work out again with a wider remit —
on top of a row the child had in fact already written. The calls that succeeded are the
part it must not repeat, so they travel with the answer."""

from __future__ import annotations

import json
from typing import Any

from my_agent_crew import texts
from my_agent_crew.store.runs import DONE, RunRecord

# The most recent successful calls are listed; the state a retry would clash with is
# usually near the end, and a child at its step cap may have made dozens.
MAX_LISTED = 12
FIELD_CHARS = 160


def unfinished_note(run: RunRecord) -> str:
    """Empty for a finished run. Otherwise the stop reason plus the calls that went
    through, so the delegator reads the answer as a fragment, not a conclusion."""
    if run.status == DONE:
        return ""
    head = texts.DELEGATE_UNFINISHED.format(status=run.status, reason=run.summary or run.status)
    succeeded = [s for s in run.steps if s.get("kind") == "tool" and s.get("ok")]
    if not succeeded:
        return f"{head}\n{texts.DELEGATE_UNFINISHED_NOTHING}"
    lines = [_line(step) for step in succeeded[-MAX_LISTED:]]
    hidden = len(succeeded) - MAX_LISTED
    if hidden > 0:
        lines.insert(0, texts.DELEGATE_UNFINISHED_EARLIER.format(count=hidden))
    return "\n".join([head, texts.DELEGATE_UNFINISHED_DONE, *lines])


def _line(step: dict[str, Any]) -> str:
    return texts.DELEGATE_UNFINISHED_LINE.format(
        name=step.get("name", "?"),
        arguments=_cut(_arguments(step.get("arguments"))),
        output=_cut(str(step.get("output") or "")),
    )


def _arguments(arguments: Any) -> str:
    """The command or path reads best bare (a timeout beside it says nothing about what
    changed); a single argument too. Anything else stays a mapping."""
    if not isinstance(arguments, dict) or not arguments:
        return str(arguments or "")
    for key in ("command", "path"):
        if key in arguments:
            return str(arguments[key])
    if len(arguments) == 1:
        return str(next(iter(arguments.values())))
    return json.dumps(arguments, ensure_ascii=False)


def _cut(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= FIELD_CHARS else text[:FIELD_CHARS] + "…"
