"""What a delegated task came to, which is not always how the child's run ended.

A child that answers "I cannot, I lack the permission" still finishes its run as `done`,
and a parent reading only the run status tells the person the job is done. The outcome
says what happened to the task instead. The runtime's facts come first: a run that did not
finish failed, and a child whose last request for approval was refused or lapsed is
blocked. Then comes what the child declared on the closing `Status:` line the always-on
`delegation` skill asks for; a child that declared nothing is done, as before.

Only `done` is handed straight to the person. Every other outcome goes back to the parent,
because the child's words were written for the agent that gave it the task."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from my_agent_crew import texts
from my_agent_crew.artifacts.tag import Tag, parse_artifact_tag
from my_agent_crew.store.approvals import DENIED, EXPIRED
from my_agent_crew.store.models import TOOL, Approval
from my_agent_crew.store.runs import DONE as RUN_DONE
from my_agent_crew.store.runs import RUNNING, RunRecord
from my_agent_crew.tools.delegate_report import cut
from my_agent_crew.tools.registry import ToolResult

DONE, DONE_WITH_CONCERNS, BLOCKED = "done", "done_with_concerns", "blocked"
NEEDS_CONTEXT, FAILED = "needs_context", "failed"
TIMEOUT = "timeout"

# Markdown around a field name or value: bold, italics, code.
_MARK = r"[*_`]*"
# What models put before a field name: a heading, a list bullet, a quote marker.
_PREFIX = r"^[ \t]*(?:#{1,6}[ \t]+)?(?:[-*>][ \t]+)?" + _MARK + r"[ \t]*"
# The two-word values come first so neither is read as DONE; `\b` refuses DONE_FOO. Models
# also write them with a space or a hyphen, and put an emoji or a backtick before them.
_STATUS = re.compile(
    _PREFIX + r"Status" + _MARK + r"[ \t]*:[^\w\n]*"
    r"(DONE[ _-]+WITH[ _-]+CONCERNS|NEEDS[ _-]+CONTEXT|DONE|BLOCKED)\b(.*)$",
    re.IGNORECASE | re.MULTILINE,
)
_SUMMARY = re.compile(
    _PREFIX + r"Summary" + _MARK + r"[ \t]*:[ \t]*" + _MARK + r"(.+)$",
    re.IGNORECASE | re.MULTILINE,
)
_FENCE = re.compile(r"^[ \t]*```.*?^[ \t]*```[ \t]*$", re.MULTILINE | re.DOTALL)
# The older contract, still taught where a child must stop for the person's consent: the
# word alone, capitalised. `blocked` in prose, UNBLOCKED and BLOCKED_BY do not count.
_BARE_BLOCKED = re.compile(r"\bBLOCKED\b(.*)$", re.MULTILINE)
_LEAD = " \t*`-—–:,.;"


@dataclass(frozen=True)
class Outcome:
    status: str
    reason: str = ""


def declared_outcome(answer: str) -> Outcome | None:
    """What the child said about its task, or None when it said nothing. The last Status
    line counts: a child that was stuck and then got through writes both. A Status line
    outranks the bare word BLOCKED anywhere in the prose.

    A code block holds what the child is showing, such as a task list or a ticket, so its
    Status lines count only when none stand outside one, and then only in capitals: that
    is a closing block the child fenced the way the skill shows it, not a file's field."""
    fences = [m.span() for m in _FENCE.finditer(answer)]
    found = list(_STATUS.finditer(answer))
    outside = [m for m in found if not any(a <= m.start() < b for a, b in fences)]
    found = outside or [m for m in found if m.group(1).isupper()]
    if found:
        last = found[-1]
        reason = _reason(last.group(2))
        if not reason:
            summary = _SUMMARY.search(answer, last.end())
            reason = _reason(summary.group(1)) if summary else ""
        return Outcome(re.sub(r"[ _-]+", "_", last.group(1)).lower(), reason)
    bare = _BARE_BLOCKED.search(answer)
    return Outcome(BLOCKED, _reason(bare.group(1))) if bare else None


def _reason(text: str) -> str:
    """One line, as short as the unfinished note's fields, so a reason can never carry a
    newline that would read as a line of the result."""
    return cut(text.lstrip(_LEAD).rstrip(" \t*`"))


def decide(run: RunRecord, declared: Outcome | None, latest: Approval | None) -> Outcome:
    """The runtime's facts outrank the child's claim. `latest` is the child's most recently
    decided tool approval: one refused tool followed by an approved one is not blocked. A
    question is never it, answered or not: one nobody answered is not a refusal (the child
    carried on with its default), and one decided after a refused tool does not undo it."""
    if run.status != RUN_DONE:
        return Outcome(FAILED, cut(run.summary or run.status))
    if latest is not None and latest.kind == TOOL and latest.status in (DENIED, EXPIRED):
        return Outcome(BLOCKED, f"{latest.tool_name} {latest.status}")
    return declared or Outcome(DONE)


def relays(outcome: Outcome) -> bool:
    return outcome.status == DONE


def outcome_line(outcome: Outcome) -> str:
    """Line 2 of the result. A reason rides along only when the task is not done."""
    if outcome.status == DONE or not outcome.reason:
        return f"outcome={outcome.status}"
    return f"outcome={outcome.status} reason={outcome.reason}"


def header_line(conv_id: str, run: RunRecord | None) -> str:
    """Line 1, which the web card reads with a regex anchored at both ends."""
    status, spent, steps = (run.status, run.spent_usd, len(run.steps)) if run else (RUNNING, 0, 0)
    return texts.DELEGATE_RESULT_HEADER.format(
        conv_id=conv_id, status=status, spent=spent or 0.0, steps=steps
    )


def result_text(header: str, outcome: str, canvases: Sequence[str], more: str, body: str) -> str:
    """Line 1, line 2, the canvases the child wrote, a blank line that is always there, the
    body. `more` counts the canvases left out and opens the body: below the blank line, so
    it is never read as one more canvas, and outside the answer handed to the person."""
    rest = f"{more}\n\n{body}" if more else body
    return "\n".join([header, outcome, *canvases, "", rest])


def canvas_tags(output: str) -> list[Tag]:
    """The canvases a result names as written by the child, read by the rule the web card
    reads them by: line 2 is the outcome, a blank line stands somewhere under it, and every
    line between the two opens with a tag. Short of any of those the result names none, so a
    tag the child quoted in its own words, under the blank line, is never one of them."""
    lines = output.split("\n")
    if len(lines) < 2 or not lines[1].startswith("outcome="):
        return []
    rest = lines[2:]
    if "" not in rest:
        return []
    tags: list[Tag] = []
    for line in rest[: rest.index("")]:
        tag = parse_artifact_tag(line)
        if tag is None:
            return []
        tags.append(tag)
    return tags


def timed_out(
    conv_id: str, run: RunRecord | None, canvases: Sequence[str], more: str
) -> ToolResult:
    """The wait ran out with the child still going. The header stays, so the card can
    still point at the child's conversation, and the parent reads a failure to report,
    with what the child had written by then named as in any other result."""
    body = texts.DELEGATE_TIMEOUT.format(conv_id=conv_id)
    header, outcome = header_line(conv_id, run), outcome_line(Outcome(FAILED, TIMEOUT))
    return ToolResult(ok=False, output=result_text(header, outcome, canvases, more, body))
