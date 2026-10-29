"""Lines of `MEMORY.md` that hold only for a while.

Some things worth remembering are true until a known day: an order on its way, a trip, a
subscription about to lapse. Such a line names that day after its own date,
`(2026-10-28 → 2026-11-02)`: the last day it holds. Past it, the line leaves the prompt at
once rather than at the next weekly rewrite, and the rewrite may drop it without anyone
approving, since what it said has stopped being true by its own account.

Giving a line an end day works the other way round: it schedules the line to vanish. For a
line just added that costs nothing, but for one already in memory it is a loss deferred,
so the rewrite gate counts it as a change a person must see (`cut_short`).
"""

from __future__ import annotations

from datetime import date

from my_agent_crew.memory.fact_dates import line_key, until_day


def is_expired(line: str, today: date) -> bool:
    last = until_day(line)
    return last is not None and last < today


def drop_expired(text: str, today: date) -> str:
    """The text without its lines past their end day, everything else as it was."""
    return "\n".join(line for line in text.splitlines() if not is_expired(line, today))


def cut_short(previous: str, new: str) -> list[str]:
    """Lines of `new` already in `previous` that now end sooner than they did: an end day
    where there was none, or an earlier one. A later end day, or the same one, is not."""
    before = {line_key(line): until_day(line) for line in previous.splitlines() if line.strip()}
    cut: list[str] = []
    for line in new.splitlines():
        key = line_key(line)
        last = until_day(line)
        if last is None or key not in before:
            continue
        earlier = before[key]
        if earlier is None or last < earlier:
            cut.append(line.strip())
    return cut
