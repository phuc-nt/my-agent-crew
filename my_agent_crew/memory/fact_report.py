"""A fact as `user_memory_get` reports it: the version that holds on the day asked, who
stands behind it, when it holds, where it came from and the versions before it."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from my_agent_crew.memory import fact_history
from my_agent_crew.memory.fact_index import BASIS_LABELS
from my_agent_crew.memory.fact_model import Fact

MAX_PAST_SHOWN = 8


def _span(fact: Fact) -> str:
    if not (fact.valid_from or fact.valid_until):
        return ""
    return f"hiệu lực: {fact.valid_from or '…'} → {fact.valid_until or '…'}"


def _head(fact: Fact) -> list[str]:
    lines = [
        f"# {fact.description or fact.name} ({fact.name}, phiên bản {fact.version})",
        f"loại: {fact.type} · {BASIS_LABELS[fact.stands_on]} · ghi bởi {fact.written_by}"
        f" · lúc {fact.updated}",
    ]
    for extra in (
        _span(fact),
        f"xác nhận lại: {fact.confirmed}" if fact.confirmed else "",
        f"nguồn: {', '.join(fact.sources)}" if fact.sources else "",
    ):
        if extra:
            lines.append(extra)
    return lines


def report(facts_dir: Path, current: Fact | None, name: str, day: date, today: date) -> str:
    """Empty when no version held on `day`."""
    past = fact_history.versions(facts_dir, name)
    held = fact_history.as_of(current, past, day)
    if held is None:
        return ""
    lines = _head(held)
    if day != today:
        lines.append(f"(đúng vào {day.isoformat()})")
    if current is not None and held is not current:
        lines.append(f"bản hiện tại: phiên bản {current.version}, {current.description}")
    lines += ["", held.body]
    if past:
        lines += ["", "lịch sử:"]
        for v in past[-MAX_PAST_SHOWN:]:
            span = _span(v.fact)
            lines.append(
                f"- v{v.fact.version} {v.fact.description} · {BASIS_LABELS[v.fact.stands_on]}"
                f" · {v.why} lúc {v.ended_at}" + (f" · {span}" if span else "")
            )
    return "\n".join(lines)
