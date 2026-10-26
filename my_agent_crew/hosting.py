"""Two switches for a host that runs the server where it may be stopped between requests,
such as a container that sleeps when idle. Such a host keeps the clock and the bot's inbox
itself, and the server only does what it is handed.

`MY_AGENT_SCHEDULER=external` leaves the clock to the host: no job fires on its own, and
the host runs a due one through `POST /api/jobs/{id}/run`. Approvals left waiting still
lapse on time, since judging that is the server's (`server/external_clock.py`).

`MY_AGENT_TELEGRAM=webhook` stops the bot polling: the host takes the bot's webhook and
hands each update over through `POST /api/channels/telegram/updates`.

Unset, both keep what a server on one machine does: its own clock, its own poll.
"""

from __future__ import annotations

from collections.abc import Mapping

SCHEDULER_ENV = "MY_AGENT_SCHEDULER"
TELEGRAM_ENV = "MY_AGENT_TELEGRAM"
INTERNAL, EXTERNAL = "internal", "external"
POLLING, WEBHOOK = "polling", "webhook"


def _mode(env: Mapping[str, str], name: str, usual: str, other: str) -> str:
    value = (env.get(name) or usual).strip().lower()
    if value not in (usual, other):
        raise ValueError(f"{name} must be {usual!r} or {other!r}, not {value!r}")
    return value


def external_clock(env: Mapping[str, str]) -> bool:
    return _mode(env, SCHEDULER_ENV, INTERNAL, EXTERNAL) == EXTERNAL


def telegram_webhook(env: Mapping[str, str]) -> bool:
    return _mode(env, TELEGRAM_ENV, POLLING, WEBHOOK) == WEBHOOK
