"""Validation and card text for a schedule proposed from chat, in one place so the tool
call and the approval card can never disagree about what is allowed.

This lives in `tools/`, not `scheduler/`, so `scheduler` never has to import Vietnamese
strings from `tools` — the dependency only runs the other way, from a tool into the cron
math it already needs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from my_agent_crew.scheduler.cron import CronSpec, parse_every
from my_agent_crew.tools.schedule_create_texts import (
    SCHEDULE_REASON_HEADER,
    SCHEDULE_REASON_PROMPT_HEADER,
    SCHEDULE_REASON_SKILLS,
    SCHEDULE_REASON_UPCOMING_HEADER,
    SCHEDULE_REASON_WHEN,
    SCHEDULE_UNWATCHED_WARNING,
)

MIN_GAP_MINUTES = 15
MAX_PROMPT = 2000
MAX_NAME = 60
MAX_PER_AGENT = 20
#: Beyond this, a proposal's second occurrence is not worth listing: a yearly cron's next
#: run is always more than a month out, and showing it anyway would just be noise.
REASON_HORIZON_DAYS = 31
#: `CronSpec.next_after`'s own limit: a schedule with no run in this many days is refused
#: outright, since it would never fire at all.
NEXT_RUN_HORIZON_DAYS = 366

_ERR_NEEDS_ONE_OF = "Cần đúng một trong hai: cron hoặc every."
_ERR_EVERY_TOO_SHORT = "every phải từ 15 phút trở lên."
_ERR_CRON_INVALID = "Biểu thức cron không hợp lệ: {error}"
_ERR_CRON_TOO_FREQUENT = "Cron này chạy dày hơn {gap} phút một lần; cần cách nhau ít nhất 15 phút."
_ERR_CRON_NEVER_RUNS = "Cron này không có lần chạy nào trong 366 ngày tới."
_ERR_NAME_TOO_LONG = f"Tên lịch dài quá {MAX_NAME} ký tự."
_ERR_PROMPT_TOO_LONG = f"Nội dung dài quá {MAX_PROMPT} ký tự."
_ERR_UNKNOWN_SKILL = "Không có skill tên {name!r}."


class ProposalError(ValueError):
    """A proposal that fails validation, with a message meant to be read as-is: it
    becomes the approval card's reason when the tool call itself was malformed."""


@dataclass(frozen=True)
class Proposal:
    name: str
    prompt: str
    cron: str | None
    every: str | None
    skills: tuple[str, ...] = ()


def min_gap_minutes(spec: CronSpec) -> int:
    """A lower bound on how close together two runs of this cron can be, from its hour and
    minute fields alone. Day, month and weekday constraints can only thin a schedule out
    further than this suggests, never make it denser — so this bound can reject a cron
    that is actually fine, but can never let a truly frequent one through."""
    slots = sorted(h * 60 + m for h in spec.hours for m in spec.minutes)
    if len(slots) <= 1:
        return 1440
    gaps = [b - a for a, b in zip(slots, slots[1:], strict=False)]
    gaps.append(1440 - slots[-1] + slots[0])
    return min(gaps)


def _validate_cron(cron: str) -> None:
    try:
        spec = CronSpec.parse(cron)
    except ValueError as exc:
        raise ProposalError(_ERR_CRON_INVALID.format(error=exc)) from exc
    gap = min_gap_minutes(spec)
    if gap < MIN_GAP_MINUTES:
        raise ProposalError(_ERR_CRON_TOO_FREQUENT.format(gap=gap))
    if spec.next_after(datetime.now(), horizon_days=NEXT_RUN_HORIZON_DAYS) is None:
        raise ProposalError(_ERR_CRON_NEVER_RUNS)


def _validate_every(every: str) -> None:
    try:
        seconds = parse_every(every)
    except ValueError as exc:
        raise ProposalError(str(exc)) from exc
    if seconds < MIN_GAP_MINUTES * 60:
        raise ProposalError(_ERR_EVERY_TOO_SHORT)


def parse(args: dict[str, Any], known_skills: tuple[str, ...]) -> Proposal:
    """The same check a tool call is judged by and a saved row is re-checked against, so
    a schedule cannot exist in the database in a shape the card never would have shown."""
    name = str(args.get("name", "")).strip()
    prompt = str(args.get("prompt", "")).strip()
    cron = args.get("cron") or None
    every = args.get("every") or None
    skills = tuple(str(s) for s in (args.get("skills") or ()))

    if bool(cron) == bool(every):  # both set, or neither
        raise ProposalError(_ERR_NEEDS_ONE_OF)
    if cron:
        _validate_cron(str(cron))
    else:
        _validate_every(str(every))
    if len(name) > MAX_NAME:
        raise ProposalError(_ERR_NAME_TOO_LONG)
    if len(prompt) > MAX_PROMPT:
        raise ProposalError(_ERR_PROMPT_TOO_LONG)
    for skill in skills:
        if skill not in known_skills:
            raise ProposalError(_ERR_UNKNOWN_SKILL.format(name=skill))
    return Proposal(
        name=name,
        prompt=prompt,
        cron=str(cron) if cron else None,
        every=str(every) if every else None,
        skills=skills,
    )


def upcoming(proposal: Proposal, now: datetime, count: int = 3) -> list[datetime]:
    """The next `count` runs, or fewer once the first is already more than
    `REASON_HORIZON_DAYS` out — a yearly cron's second occurrence is always that far away,
    and listing it anyway would just pad the card with a date nobody needed."""
    if proposal.every:
        step = timedelta(seconds=parse_every(proposal.every))
        return [now + step * k for k in range(1, count + 1)]
    spec = CronSpec.parse(proposal.cron or "")
    out: list[datetime] = []
    last = now
    for _ in range(count):
        nxt = spec.next_after(last, horizon_days=NEXT_RUN_HORIZON_DAYS)
        if nxt is None:
            break
        out.append(nxt)
        if not out[1:] and (nxt - now).days > REASON_HORIZON_DAYS:
            break
        last = nxt
    return out


def _schedule_words(proposal: Proposal) -> str:
    return f"mỗi {proposal.every}" if proposal.every else "theo cron"


def reason_line(proposal: Proposal, now: datetime) -> str:
    """The approval card's whole content, as one string: it is the only place a person
    reads the prompt (the web card and Telegram both render `reason` verbatim and nothing
    else), so it carries the name, the schedule in words, the next few runs, any attached
    skills, the verbatim prompt and the one-sentence warning about unwatched runs."""
    written = proposal.cron or proposal.every or ""
    parts = [
        SCHEDULE_REASON_HEADER.format(name=proposal.name or "(chưa đặt tên)"),
        SCHEDULE_REASON_WHEN.format(words=_schedule_words(proposal), written=written),
    ]
    runs = upcoming(proposal, now, count=3)
    if runs:
        parts.append(SCHEDULE_REASON_UPCOMING_HEADER)
        parts.extend(f"- {when.strftime('%d/%m %H:%M')}" for when in runs)
    if proposal.skills:
        parts.append(SCHEDULE_REASON_SKILLS.format(skills=", ".join(proposal.skills)))
    parts.append(SCHEDULE_REASON_PROMPT_HEADER)
    parts.append(proposal.prompt)
    parts.append(SCHEDULE_UNWATCHED_WARNING)
    return "\n".join(parts)
