"""A schedule's timing in words, read the way the scheduler reads a cron field (minute hour
day month weekday, local time, 0 and 7 both Sunday) — the same convention and the same
phrasing as `web/src/lib/cron-text.ts`, which already renders every schedule listed in the
Jobs tab this way. Kept in step with that file by hand: there is no runtime shared between
Python and the web bundle to import this from instead.

Anything outside the shapes below comes back exactly as written. A paraphrase that is nearly
right — "every day" for a cron that also names a month — is worse than the raw string,
because a person reading an approval card believes the words over the expression beside
them."""

from __future__ import annotations

import re

_UNIT_WORDS = {"s": "giây", "m": "phút", "h": "giờ", "d": "ngày"}
_DAY_NAMES = ["Chủ Nhật", "Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy"]
_EVERY = re.compile(r"^(\d+)\s*([smhd])$")


def _every_words(n: int, unit: str) -> str:
    word = _UNIT_WORDS[unit]
    return f"Mỗi {word}" if n == 1 else f"Mỗi {n} {word}"


def _num(text: str, low: int, high: int) -> int | None:
    if not text.isdigit():
        return None
    n = int(text)
    return n if low <= n <= high else None


def _step(text: str, cycle: int) -> int | None:
    """The N of a `*/N` that evenly divides `cycle` (60 minutes, 24 hours) — only a divisor
    keeps every gap equal, which "every N" promises; the scheduler otherwise restarts the
    step at the next hour or midnight, shortening the last gap."""
    match = re.fullmatch(r"\*/(\d+)", text)
    n = _num(match.group(1), 1, cycle - 1) if match else None
    return n if n is not None and cycle % n == 0 else None


def _list(text: str, low: int, high: int) -> list[int] | None:
    values = [_num(part, low, high) for part in text.split(",")]
    return None if any(v is None for v in values) else [v for v in values if v is not None]


def _weekdays(text: str) -> set[int] | None:
    days: set[int] = set()
    for part in text.split(","):
        pieces = part.split("-", 1)
        from_text, to_text = pieces[0], pieces[1] if len(pieces) > 1 else pieces[0]
        start, end = _num(from_text, 0, 7), _num(to_text, 0, 7)
        if start is None or end is None or start > end:
            return None
        days.update(day % 7 for day in range(start, end + 1))
    return days


def _on_days(days: set[int], time: str) -> str:
    if len(days) == 7:
        return f"Mỗi ngày {time}"
    key = ",".join(str(d) for d in sorted(days))
    if key == "1,2,3,4,5":
        return f"Thứ Hai–Thứ Sáu {time}"
    if key == "0,6":
        return f"Cuối tuần {time}"
    names = [_DAY_NAMES[d] for d in [1, 2, 3, 4, 5, 6, 0] if d in days]  # Monday first, Sunday last
    return f"{', '.join(names)} hằng tuần {time}"


def _repeating(minute: str, hour: str) -> str | None:
    """The hourly shapes: every minute, every N minutes, every hour or every N hours."""
    if hour == "*":
        if minute == "*":
            return _every_words(1, "m")
        minutes = _step(minute, 60)
        if minutes is not None:
            return _every_words(minutes, "m")
    hours = 1 if hour == "*" else _step(hour, 24)
    at = _num(minute, 0, 59)
    if hours is None or at is None:
        return None
    every = _every_words(hours, "h")
    return every if at == 0 else f"{every} vào phút {at}"


def cron_words(cron: str) -> str:
    """ "Mỗi ngày 07:00" for `0 7 * * *`; the cron itself for a shape not listed here."""
    fields = cron.strip().split()
    if len(fields) != 5:
        return cron
    minute, hour, day, month, weekday = fields
    if month != "*":
        return cron
    if day == "*" and weekday == "*":
        often = _repeating(minute, hour)
        if often is not None:
            return often
    at = _num(minute, 0, 59)
    hours = _list(hour, 0, 23)
    if at is None or hours is None:
        return cron
    time = ", ".join(f"{h:02d}:{at:02d}" for h in hours)
    if day == "*":
        days = set(range(7)) if weekday == "*" else _weekdays(weekday)
        return _on_days(days, time) if days is not None else cron
    date = _num(day, 1, 31)
    return f"Ngày {date} hằng tháng {time}" if date is not None and weekday == "*" else cron


def every_words(every: str) -> str:
    """ "Mỗi 30 phút" for the `every: 30m` shorthand, in the units the scheduler accepts."""
    match = _EVERY.match(every.strip().lower())
    return _every_words(int(match.group(1)), match.group(2)) if match else every


def schedule_words(cron: str | None, every: str | None) -> str:
    """A schedule's timing in words, whichever of the two keys it is written with."""
    if cron:
        return cron_words(cron)
    return every_words(every) if every else ""
