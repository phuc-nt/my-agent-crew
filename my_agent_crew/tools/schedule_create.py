"""`schedule_create`: an agent proposing a repeating job, for a person to approve.

No `agent` parameter — a schedule always belongs to whichever agent called the tool, never
to one it names. Letting the caller pick a target would mean a prompt one agent wrote runs
later under another agent's allow-list, persona and cost cap; scheduling *another* agent's
work still only happens by hand, in that agent's own `agent.yaml`.

`ask_reason` is what makes approval unconditional (see `agent/tool_gate.py`): it is asked
before the gate even looks at autonomy, `auto_approve` or the allow list, and it is never
empty — a proposal that fails validation, or one from an agent already at its cap, still
produces a card, just one whose reason is that error instead of the schedule. A useless
card, but a truthful one."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from my_agent_crew.agent.turn_context import turn_conversation_id
from my_agent_crew.store.created_schedules import ScheduleLimitError
from my_agent_crew.store.db import Store
from my_agent_crew.tools.registry import Tool
from my_agent_crew.tools.schedule_create_texts import (
    SCHEDULE_CREATE_DESCRIPTION,
    SCHEDULE_CREATED,
    SCHEDULE_CREATED_NO_UPCOMING,
    SCHEDULE_CRON_DESCRIPTION,
    SCHEDULE_EVERY_DESCRIPTION,
    SCHEDULE_LIMIT_REACHED,
    SCHEDULE_NAME_DESCRIPTION,
    SCHEDULE_PROMPT_DESCRIPTION,
    SCHEDULE_SKILLS_DESCRIPTION,
)
from my_agent_crew.tools.schedule_proposal import (
    MAX_PER_AGENT,
    Proposal,
    ProposalError,
    parse,
    reason_line,
    upcoming,
)

SCHEDULE_CREATE_TOOL_NAME = "schedule_create"


def _schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": SCHEDULE_NAME_DESCRIPTION},
            "prompt": {"type": "string", "description": SCHEDULE_PROMPT_DESCRIPTION},
            "cron": {"type": "string", "description": SCHEDULE_CRON_DESCRIPTION},
            "every": {"type": "string", "description": SCHEDULE_EVERY_DESCRIPTION},
            "skills": {
                "type": "array",
                "items": {"type": "string"},
                "description": SCHEDULE_SKILLS_DESCRIPTION,
            },
        },
        "required": ["name", "prompt"],
    }


def _next_run_text(proposal: Proposal, now: datetime) -> str:
    [first] = upcoming(proposal, now, count=1) or [None]
    return first.strftime("%d/%m %H:%M") if first else ""


def build_schedule_create_tool(
    store: Store,
    agent_id: str,
    known_skills: tuple[str, ...],
    clock: Callable[[], datetime],
) -> Tool:
    def ask_reason(arguments: dict[str, Any]) -> str:
        """Never empty: a proposal that parses becomes the full card; one that does not,
        or one this agent has no room left for, becomes its own error, read as the
        reason instead. The cap is a courtesy here — `run` checks it again, atomically,
        because another approval can land between the card and this one."""
        try:
            proposal = parse(arguments, known_skills)
        except ProposalError as exc:
            return str(exc)
        if store.created_schedules.count(agent_id) >= MAX_PER_AGENT:
            return SCHEDULE_LIMIT_REACHED.format(cap=MAX_PER_AGENT)
        return reason_line(proposal, clock())

    async def run(arguments: dict[str, Any]) -> str:
        """Re-validates rather than trusting the reason a person already read: the two
        must never disagree, and re-running the same pure check is how that is kept true
        without storing the parsed proposal anywhere between the ask and the run."""
        try:
            proposal = parse(arguments, known_skills)
        except ProposalError as exc:
            return str(exc)
        row = {
            "agent_id": agent_id,
            "name": proposal.name,
            "cron": proposal.cron,
            "every": proposal.every,
            "prompt": proposal.prompt,
            "skills": list(proposal.skills),
            "created_by_conversation": turn_conversation_id(),
        }
        try:
            created = store.created_schedules.add(row, cap=MAX_PER_AGENT)
        except ScheduleLimitError:
            return SCHEDULE_LIMIT_REACHED.format(cap=MAX_PER_AGENT)
        next_run = _next_run_text(proposal, clock())
        if next_run:
            return SCHEDULE_CREATED.format(name=proposal.name, id=created.id, next_run=next_run)
        return SCHEDULE_CREATED_NO_UPCOMING.format(name=proposal.name, id=created.id)

    return Tool(
        SCHEDULE_CREATE_TOOL_NAME,
        SCHEDULE_CREATE_DESCRIPTION,
        _schema(),
        run,
        requires_approval=True,
        ask_reason=ask_reason,
    )
