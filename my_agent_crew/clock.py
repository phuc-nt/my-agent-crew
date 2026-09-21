"""One clock for the crew. The store stamps runs and messages in UTC; every "today" an
agent reasons about and every time shown to the person are read in the person's zone:
`timezone` in config.yaml (an IANA name such as `Asia/Ho_Chi_Minh`) or, unset, the
machine's own. The server may run anywhere; the person lives in one place."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def zone_for(name: str) -> tzinfo:
    """The zone a name stands for; an empty name means the machine's. An unknown name is
    a configuration error raised where settings load, not at 03:00 inside a job."""
    if not name.strip():
        return datetime.now().astimezone().tzinfo  # type: ignore[return-value]
    try:
        return ZoneInfo(name.strip())
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"timezone: unknown zone {name!r}") from exc


def local_day(stamp: str, zone: tzinfo | None) -> str:
    """The calendar day (`YYYY-MM-DD`) a stored UTC stamp falls on in the zone."""
    return datetime.fromisoformat(stamp).astimezone(zone).date().isoformat()


def day_start_utc(day: date, zone: tzinfo) -> str:
    """Midnight of a local day as the UTC stamp the store compares against."""
    start = datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)
    return start.isoformat(timespec="seconds")
