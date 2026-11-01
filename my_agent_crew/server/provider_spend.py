"""What each model provider has cost, for the figure the header keeps in view.

Two sources. The crew's own ledger (`store/usage.py`) is every call this server made,
priced as it answered, cut to today and this month in the person's zone. OpenRouter's
key info is the provider's own count for the key, which also includes calls made with the
same key elsewhere, and says what is left under the key's limit; it is free to read and
asked at most once a minute. Anthropic has nothing an ordinary API key can read spend or
credit from (its cost report wants an organisation's admin key), so its figure is the
ledger's. A report that cannot be had is None, never a zero that would read as "nothing
spent".
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from datetime import date, tzinfo
from typing import Any

import httpx

from my_agent_crew.clock import day_start_utc
from my_agent_crew.server.credential_checks import OPENROUTER_KEY_URL
from my_agent_crew.store.usage import UsageStore

REPORT_SECONDS = 60.0
REPORT_TIMEOUT_SECONDS = 8.0
# The key info's money fields, all USD; `limit` and `limit_remaining` are null on a key
# with no limit.
OPENROUTER_FIGURES = (
    "usage",
    "usage_daily",
    "usage_weekly",
    "usage_monthly",
    "limit",
    "limit_remaining",
)
# The providers that bill, first in the order the header lists them.
BILLED_ORDER = ("anthropic", "openrouter")

_reports: dict[str, tuple[float, dict[str, Any] | None]] = {}


def _money(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


async def openrouter_report(client: httpx.AsyncClient, key: str) -> dict[str, Any] | None:
    """The key's spend and limit as OpenRouter counts them; None when it cannot be read."""
    try:
        response = await client.get(
            OPENROUTER_KEY_URL,
            headers={"Authorization": f"Bearer {key}"},
            timeout=REPORT_TIMEOUT_SECONDS,
        )
        body = response.json() if response.is_success else None
    except (httpx.HTTPError, ValueError):
        return None
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        return None
    report: dict[str, Any] = {name: _money(data.get(name)) for name in OPENROUTER_FIGURES}
    reset = data.get("limit_reset")
    report["limit_reset"] = reset if isinstance(reset, str) else None
    return report


async def cached_openrouter_report(
    client: httpx.AsyncClient, key: str, clock: Callable[[], float] = time.monotonic
) -> dict[str, Any] | None:
    """`openrouter_report`, kept a minute so a header polling it costs one request a minute
    however many pages are open. A failure is kept as long, so a dead network is not hammered."""
    held = _reports.get(key)
    if held is not None and clock() - held[0] < REPORT_SECONDS:
        return held[1]
    report = await openrouter_report(client, key)
    _reports.clear()
    _reports[key] = (clock(), report)
    return report


def forget_reports() -> None:
    _reports.clear()


def ledger_rows(
    usage: UsageStore, today: date, zone: tzinfo, billed: Iterable[str]
) -> list[dict[str, Any]]:
    """One row per provider: today's and this month's spend from the ledger. A provider with
    a key shows even before its first call, so a zero reads as "nothing yet", not "missing"."""
    month = usage.by_provider(day_start_utc(today.replace(day=1), zone))
    day = usage.by_provider(day_start_utc(today, zone))
    names = set(month) | set(billed)
    ordered = [n for n in BILLED_ORDER if n in names] + sorted(names - set(BILLED_ORDER))
    rows = []
    for name in ordered:
        totals = month.get(name, {})
        rows.append(
            {
                "provider": name,
                "today_usd": round(day.get(name, {}).get("cost_usd", 0.0), 6),
                "month_usd": round(totals.get("cost_usd", 0.0), 6),
                "calls": totals.get("calls", 0),
                "unknown_cost_calls": totals.get("unknown_cost_calls", 0),
            }
        )
    return rows
