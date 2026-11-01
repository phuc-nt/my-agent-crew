"""What the agent is told about a person's decision on a call it had to wait for.

A call that ran after its approval used to come back as any other result, so the model
told the person nothing had asked them; a refusal did not say whether a person turned it
down or the wait ran out. These words close that gap, naming where the person decided
when it is known (`Approval.decided_via`)."""

from __future__ import annotations

from my_agent_crew.store.approvals import APPROVED, DENIED, EXPIRED
from my_agent_crew.store.models import Approval
from my_agent_crew.texts import DENIED_TOOL, EXPIRED_TOOL
from my_agent_crew.texts_approval import (
    APPROVED_NOTE,
    DECIDED_VIA,
    DELEGATE_DENIED_REASON,
    DELEGATE_EXPIRED_REASON,
    DENIED_NOTE,
)

REFUSALS = {DENIED: DENIED_TOOL, EXPIRED: EXPIRED_TOOL}


def via_words(approval: Approval) -> str:
    """Where the person decided, in words; "" when unknown."""
    return DECIDED_VIA.get(approval.decided_via, "")


def refusal_text(approval: Approval) -> str:
    """The result of a refused call. Each keeps its fixed opening, which readers match;
    a denial a person made somewhere known says where after it."""
    text = REFUSALS[approval.status]
    via = via_words(approval)
    if approval.status == DENIED and via:
        return f"{text} {DENIED_NOTE.format(via=via)}"
    return text


def with_approval_note(output: str, approval: Approval | None) -> str:
    """A result of a call a person approved, with that said under it."""
    if approval is None or approval.status != APPROVED:
        return output
    note = " ".join(APPROVED_NOTE.format(via=via_words(approval)).split())
    return f"{output}\n\n{note}" if output else note


def delegate_reason(approval: Approval) -> str:
    """Why a child is blocked, as the delegation result says it: a person's no, and where,
    told apart from a request nobody answered in time."""
    if approval.status == EXPIRED:
        return DELEGATE_EXPIRED_REASON.format(tool=approval.tool_name)
    reason = DELEGATE_DENIED_REASON.format(tool=approval.tool_name, via=via_words(approval))
    return reason.strip()
