"""What one `agent.yaml` says of the browser: whether the agent may read pages or also act on
them, and the hosts it goes to without asking. Both are read from the agent's own file and
never from the settings it inherits, so a browser is on only where somebody wrote so."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from my_agent_crew.config_browser import (
    BROWSER_ACT,
    BROWSER_MODES,
    BROWSER_OFF,
    BROWSER_READ,
    BrowserSettings,
)

# A host name or an IPv4 address, or `*.` and a suffix. Lowercase ASCII (an international
# name in its punycode form), no scheme, port or path: the port a page is served on does not
# change whose page it is.
HOST_PATTERN = re.compile(r"^(\*\.)?([a-z0-9-]+\.)*[a-z0-9-]+$")


def browser_of(raw: dict[str, Any], agent_id: str, base: BrowserSettings) -> BrowserSettings:
    return replace(base, mode=_mode(raw, agent_id), hosts=_hosts(raw, agent_id))


def _mode(raw: dict[str, Any], agent_id: str) -> str:
    value = raw.get("browser", BROWSER_OFF)
    known = f"agent {agent_id}: browser must be {BROWSER_OFF}, {BROWSER_READ} or {BROWSER_ACT}"
    # YAML reads a bare `off`, `no` or `false` as this, and each of them means what it says.
    if value is None or value is False:
        return BROWSER_OFF
    if value is True:
        # A bare `on`, `yes` or `true`: on, but nobody said how far.
        raise ValueError(
            f"{known}, not a bare on, yes or true: write {BROWSER_READ} to let it open and"
            f" read pages, or {BROWSER_ACT} to let it click and type as well"
        )
    if value not in BROWSER_MODES:
        raise ValueError(known)
    return value


def _hosts(raw: dict[str, Any], agent_id: str) -> tuple[str, ...]:
    refusal = ValueError(
        f"agent {agent_id}: browser_hosts must be a list of host names such as shop.example"
        " or *.shop.example, in lowercase, with no scheme, port or path"
    )
    value = raw.get("browser_hosts") or []
    if not isinstance(value, list):
        raise refusal
    hosts = []
    for entry in value:
        if not isinstance(entry, str) or not HOST_PATTERN.match(entry.strip()):
            raise refusal
        hosts.append(entry.strip())
    return tuple(hosts)
