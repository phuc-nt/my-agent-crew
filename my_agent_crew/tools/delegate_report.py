"""What a delegated child left behind, beside its answer.

A child that stops at its step cap, on an error or on an interruption hands back its last
words, which are often half a thought ("that table does not exist…"). Read alone they say
nothing happened, and the delegator hands the same work out again with a wider remit —
on top of a row the child had in fact already written. The calls that succeeded are the
part it must not repeat, so they travel with the answer.

The canvases it wrote are named whether it finished or not. A canvas outlives the child's
conversation, and the delegator can tell the person only about one it knows is there."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from my_agent_crew import texts
from my_agent_crew.artifacts.tag import artifact_tag
from my_agent_crew.store.runs import DONE, RunRecord

if TYPE_CHECKING:
    from my_agent_crew.store.artifact_usage import ArtifactUsage

# The most recent successful calls are listed; the state a retry would clash with is
# usually near the end, and a child at its step cap may have made dozens.
MAX_LISTED = 12
FIELD_CHARS = 160


def unfinished_note(run: RunRecord) -> str:
    """Empty for a finished run. Otherwise the stop reason plus the calls that went
    through, so the delegator reads the answer as a fragment, not a conclusion. The reason
    is free text, a provider's error or the question the child stopped at, so it is quoted
    like the calls under it: `cut` keeps it from adding lines of its own to the result."""
    if run.status == DONE:
        return ""
    reason = cut(run.summary or run.status)
    head = texts.DELEGATE_UNFINISHED.format(status=run.status, reason=reason)
    succeeded = [s for s in run.steps if s.get("kind") == "tool" and s.get("ok")]
    if not succeeded:
        return f"{head}\n{texts.DELEGATE_UNFINISHED_NOTHING}"
    lines = [_line(step) for step in succeeded[-MAX_LISTED:]]
    hidden = len(succeeded) - MAX_LISTED
    if hidden > 0:
        lines.insert(0, texts.DELEGATE_UNFINISHED_EARLIER.format(count=hidden))
    return "\n".join([head, texts.DELEGATE_UNFINISHED_DONE, *lines])


def canvas_lines(artifacts: ArtifactUsage, conversation_id: str) -> tuple[list[str], str]:
    """A line for each canvas an agent wrote in the conversation, the first written first and
    MAX_LISTED at most, then the sentence that counts the rest, empty when none are left out.
    A line is the tag a canvas tool's own result opens with, then the title; the title is the
    child's wording, and `cut` keeps it to that one line."""
    written = artifacts.written_in(conversation_id)
    lines = [f"{artifact_tag(w.id, w.version)} {cut(w.title)}" for w in written[:MAX_LISTED]]
    hidden = len(written) - MAX_LISTED
    return lines, texts.DELEGATE_CANVAS_MORE.format(n=hidden) if hidden > 0 else ""


def _line(step: dict[str, Any]) -> str:
    return texts.DELEGATE_UNFINISHED_LINE.format(
        name=step.get("name", "?"),
        arguments=cut(_arguments(step.get("arguments"))),
        output=cut(str(step.get("output") or "")),
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


def cut(text: str) -> str:
    """One line, at most FIELD_CHARS long, for a field quoted inside a delegation result."""
    text = " ".join(text.split())
    return text if len(text) <= FIELD_CHARS else text[:FIELD_CHARS] + "…"
