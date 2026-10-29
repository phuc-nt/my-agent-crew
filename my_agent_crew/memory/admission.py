"""Which lines a `MEMORY.md` rewrite may add, for an agent with a memory budget.

Left to itself, a rewrite adds whatever the notes mention, and in practice that includes
what the agent can look up again whenever it needs to: where an order is, a balance, next
week's events. Such a line goes stale within days and takes the room that memory, carried
into every turn, has for preferences, rules and lessons. So an agent given
`memory_budget_chars` has each line its rewrite adds put to a second, short model call
that sees only those lines and answers, per line, to let it in or turn it away.

Turned-away lines leave the proposal before the gate looks at it. Nothing a person had is
lost that way: the lines were never in memory, and the notes and conversations they came
from stay where they are. Lines already in memory are not screened again; dropping one is
still the rewrite's to propose and the gate's to hold. The budget itself is the gate's
too (`rewrite_proposal`): what is still over it after screening waits for a person,
since cutting it down means choosing what to forget.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from my_agent_crew import texts
from my_agent_crew.llm.metered_chain import MeteredChain
from my_agent_crew.llm.types import Completion, Message
from my_agent_crew.memory.fact_dates import line_key

if TYPE_CHECKING:  # the loop imports memory, not the other way round
    from my_agent_crew.agent.loop import AgentDeps

logger = logging.getLogger(__name__)

# Lines put to the screen per rewrite, at most; any further new lines are let in, and the
# budget still holds a rewrite that grew too long.
MAX_SCREENED = 40
_VERDICT = re.compile(r"^\W*(\d+)\W*\s*(NHẬN|BỎ)\b\s*:?\s*(.*)$", re.IGNORECASE)
_TURN_AWAY = "BỎ"


@dataclass(frozen=True)
class Screened:
    """The rewrite with the turned-away lines taken out, the reasons with one entry added
    per such line, and the screen's own completion for the run to show and count."""

    body: str
    reasons: str
    completion: Completion | None = None
    turned_away: list[str] = field(default_factory=list)


def added_lines(previous: str, new: str) -> list[int]:
    """Indexes into `new.splitlines()` of the bullets that say something `previous` did
    not. A line whose only change is its date says nothing new and is not screened."""
    known = {line_key(line) for line in previous.splitlines() if line.strip()}
    return [
        i
        for i, line in enumerate(new.splitlines())
        if line.lstrip().startswith(("-", "*")) and line_key(line) not in known
    ]


def verdicts(reply: str, count: int) -> dict[int, str]:
    """The lines turned away, by their number from 1, each with the reason given. A line
    the reply says nothing clear about is let in: the screen narrows, it never adds."""
    away: dict[int, str] = {}
    for raw in reply.splitlines():
        match = _VERDICT.match(unicodedata.normalize("NFC", raw.strip()))
        if not match or not 1 <= int(match[1]) <= count:
            continue
        if match[2].upper() == _TURN_AWAY:
            away[int(match[1])] = match[3].strip().strip("`") or texts.ADMISSION_NO_REASON
    return away


async def _ask(deps: AgentDeps, lines: list[str]) -> Completion | None:
    profile = deps.agent
    numbered = "\n".join(f"{n}. {line.strip()}" for n, line in enumerate(lines, 1))
    prompt = Message(
        role="user",
        content=texts.ADMISSION_PROMPT.format(
            agent=profile.name, description=profile.description or profile.id, lines=numbered
        ),
    )
    chain = MeteredChain(deps.chain, deps.store, profile.id, "consolidate")
    completion: Completion | None = None
    async for item in chain.stream([prompt], []):
        if isinstance(item, Completion):
            completion = item
    return completion


def _with(reasons: str, notes: list[str]) -> str:
    return "\n".join([reasons, *notes]) if reasons else "\n".join(notes)


async def screen(deps: AgentDeps, previous: str, new: str, reasons: str) -> Screened:
    """Put the lines `new` adds over `previous` to the model and take out those it turns
    away. A failed call keeps every line and says so in the reasons."""
    rows = new.splitlines()
    picked = added_lines(previous, new)[:MAX_SCREENED]
    if not picked:
        return Screened(new, reasons)
    try:
        completion = await _ask(deps, [rows[i] for i in picked])
    except Exception:  # the screen failing must not cost the night's rewrite
        logger.exception("admission screen failed for agent %s", deps.agent.id)
        completion = None
    if completion is None:
        return Screened(new, _with(reasons, [texts.ADMISSION_FAILED]))

    away = verdicts(completion.message.content, len(picked))
    dropped = {picked[n - 1]: why for n, why in away.items()}
    body = "\n".join(row for i, row in enumerate(rows) if i not in dropped)
    notes = [
        texts.ADMISSION_TURNED_AWAY.format(line=rows[i].strip().lstrip("-* "), why=why)
        for i, why in sorted(dropped.items())
    ]
    return Screened(
        body.strip(),
        _with(reasons, notes) if notes else reasons,
        completion,
        [rows[i].strip() for i in sorted(dropped)],
    )
