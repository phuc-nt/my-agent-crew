"""Where an agent's browser may still be signed in, told from its cookies without reading one.

Of a cookie only the host it is for and the moment it runs out are ever taken: never its name,
never its value. One counts when no script on a page can read it, it outlasts the browser and
it is not sent along to other sites, which is how a site keeps a person signed in and not how
an advertiser follows one. It is a sign and no proof: a site may have signed the person out on
its own side, and some keep such a cookie for a visitor who never signed in.

A browser that is down cannot be asked, so what was found is written beside the profile each
time a browser on it closes, and read from there until one is up again."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

FILE = "crew-logins.json"
READ_SECONDS = 2.0
# An agent with no hosts of its own is told of this many at most, the first by name.
TOLD = 50


def kept(cookies: Iterable[dict[str, Any]], now: float) -> dict[str, float]:
    """Each host that has a cookie that counts, and when the last of them runs out."""
    hosts: dict[str, float] = {}
    for cookie in cookies:
        expires, host = cookie.get("expires"), str(cookie.get("domain") or "").lstrip(".").lower()
        if not host or cookie.get("httpOnly") is not True or cookie.get("sameSite") == "None":
            continue
        # A cookie that ends with the browser says -1 here.
        if isinstance(expires, int | float) and expires > now:
            hosts[host] = max(hosts.get(host, 0.0), float(expires))
    return hosts


async def read(context: Any) -> dict[str, float] | None:
    """What a browser that is up holds now; None from one that will not say."""
    try:
        cookies = await asyncio.wait_for(context.cookies(), READ_SECONDS)
    except Exception:  # noqa: BLE001 - a browser that closed, crashed or hangs tells nothing
        return None
    return kept(cookies, time.time())


def _write(profile: Path, hosts: dict[str, float]) -> None:
    half = profile / f"{FILE}.part"
    with os.fdopen(os.open(half, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as handle:
        json.dump({"hosts": hosts}, handle)
    os.replace(half, profile / FILE)


async def remember(
    context: Any, profile: Path | None, held: dict[str, float] | None = None
) -> None:
    """Write down what a browser that is about to close holds. Of one that will not say, and
    of one that is gone already (no `context`), `held` is written, what it was last seen to
    hold; where nobody saw, what was written before stays."""
    hosts = await read(context) if context is not None and profile is not None else None
    hosts = held if hosts is None else hosts
    if profile is None or hosts is None:
        return
    try:
        await asyncio.to_thread(_write, profile, hosts)
    except OSError as error:
        log.warning("what the browser on %s is signed in to was not written: %s", profile, error)


def recalled(profile: Path) -> dict[str, float] | None:
    """What was written when a browser on the profile last closed; None when none ever did."""
    try:
        hosts = json.loads((profile / FILE).read_text())["hosts"]
        return {str(host): float(until) for host, until in hosts.items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def _covers(pattern: str, host: str) -> bool:
    """Whether a cookie for `host` is one a page of the agent's own host would be sent, or
    one a page under it set."""
    base = pattern.removeprefix("*.")
    return host == base or host.endswith(f".{base}") or base.endswith(f".{host}")


def _when(until: float) -> str:
    return datetime.fromtimestamp(until, UTC).isoformat(timespec="seconds")


def told(hosts: dict[str, float], own: Sequence[str], now: float) -> list[dict[str, str | None]]:
    """What a person is shown. An agent with hosts of its own is told of each of them, also of
    one that holds nothing; an agent with none is told of the hosts that hold something."""
    live = {host: until for host, until in hosts.items() if until > now}
    if own:
        last = {p: max((u for h, u in live.items() if _covers(p, h)), default=None) for p in own}
        return [{"host": p, "until": _when(u) if u else None} for p, u in last.items()]
    return [{"host": host, "until": _when(live[host])} for host in sorted(live)[:TOLD]]
