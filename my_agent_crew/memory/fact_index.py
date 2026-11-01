"""The table of contents of the facts, as the prompt shows it on a given day.

One line per fact: its description, type and who stands behind it. A fact past its last
day is left out; one whose first day has not come shows the version that holds today and
what replaces it from when, so an agent neither acts on a change too early nor forgets
that it is coming. The text changes only when a fact does or a day boundary is crossed,
which the prompt cache can afford.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from my_agent_crew.memory import fact_history
from my_agent_crew.memory.fact_model import EXTRACTED, INFERRED, OPERATOR, SAID, Fact, state_on

BASIS_LABELS = {
    OPERATOR: "người dùng tự ghi",
    SAID: "người dùng nói",
    INFERRED: "agent suy ra",
    EXTRACTED: "trích tự động",
}


def _line(fact: Fact, name: str, tail: str = "") -> str:
    label = BASIS_LABELS[fact.stands_on]
    return f"- [{fact.description or name}]({name}.md) · {fact.type} · {label}{tail}"


def render(facts_dir: Path, facts: list[Fact], today: date) -> str:
    lines: list[str] = []
    for fact in facts:
        state = state_on(fact, today)
        if state == "expired":
            continue
        until = f" · đến {fact.valid_until}" if fact.valid_until else ""
        if state == "current":
            lines.append(_line(fact, fact.name, until))
            continue
        coming = f" → từ {fact.valid_from}: {fact.description or fact.name}"
        held = fact_history.as_of(None, fact_history.versions(facts_dir, fact.name), today)
        if held is None:
            lines.append(_line(fact, fact.name, f" · từ {fact.valid_from}{until}"))
        else:
            lines.append(_line(held, fact.name, coming))
    return "\n".join(lines)
