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
from dataclasses import dataclass

from my_agent_crew import texts
from my_agent_crew.store.approvals import DENIED, EXPIRED
from my_agent_crew.store.models import TOOL, Approval
from my_agent_crew.store.runs import DONE as RUN_DONE
from my_agent_crew.store.runs import RUNNING, RunRecord
from my_agent_crew.tools.delegate_report import cut
from my_agent_crew.tools.registry import ToolResult

DONE, DONE_WITH_CONCERNS, BLOCKED = "done", "done_with_concerns", "blocked"
NEEDS_CONTEXT, FAILED = "needs_context", "failed"
TIMEOUT = "timeout"

# What models put before a field name: a list bullet, a quote marker, bold.
_PREFIX = r"^[ \t]*(?:[-*>][ \t]+)?\**[ \t]*"
# DONE_WITH_CONCERNS comes first so it is never read as DONE; `\b` refuses DONE_FOO.
_STATUS = re.compile(
    _PREFIX + r"Status[ \t]*:[ \t]*\**[ \t]*"
    r"(DONE_WITH_CONCERNS|DONE|BLOCKED|NEEDS_CONTEXT)\b(.*)$",
    re.IGNORECASE | re.MULTILINE,
)
_SUMMARY = re.compile(_PREFIX + r"Summary[ \t]*:[ \t]*\**(.+)$", re.IGNORECASE | re.MULTILINE)
# The older contract, still taught where a child must stop for the person's consent: the
# word alone, capitalised. `blocked` in prose, UNBLOCKED and BLOCKED_BY do not count.
_BARE_BLOCKED = re.compile(r"\bBLOCKED\b(.*)$", re.MULTILINE)
_LEAD = " \t*-—–:,.;"


@dataclass(frozen=True)
class Outcome:
    status: str
    reason: str = ""


def declared_outcome(answer: str) -> Outcome | None:
    """What the child said about its task, or None when it said nothing. The last Status
    line counts: a child that was stuck and then got through writes both. A Status line
    outranks the bare word BLOCKED anywhere in the prose."""
    found = list(_STATUS.finditer(answer))
    if found:
        last = found[-1]
        reason = _reason(last.group(2))
        if not reason:
            summary = _SUMMARY.search(answer, last.end())
            reason = _reason(summary.group(1)) if summary else ""
        return Outcome(last.group(1).lower(), reason)
    bare = _BARE_BLOCKED.search(answer)
    return Outcome(BLOCKED, _reason(bare.group(1))) if bare else None


def _reason(text: str) -> str:
    """One line, as short as the unfinished note's fields, so a reason can never carry a
    newline that would read as a line of the result."""
    return cut(text.lstrip(_LEAD).rstrip(" \t*"))


def decide(run: RunRecord, declared: Outcome | None, latest: Approval | None) -> Outcome:
    """The runtime's facts outrank the child's claim. `latest` is the child's most recently
    decided approval: one refused tool followed by an approved one is not blocked, and a
    question nobody answered is not a refusal (the child carried on with its default)."""
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


def timed_out(conv_id: str, run: RunRecord | None) -> ToolResult:
    """The wait ran out with the child still going. The header stays, so the card can
    still point at the child's conversation, and the parent reads a failure to report."""
    lines = (
        header_line(conv_id, run),
        outcome_line(Outcome(FAILED, TIMEOUT)),
        texts.DELEGATE_TIMEOUT.format(conv_id=conv_id),
    )
    return ToolResult(ok=False, output="\n".join(lines))
