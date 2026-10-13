"""What one `agent.yaml` says of the desktop: whether the agent may use the machine's screen
and keyboard, and the applications it may read the elements of and act on. Both are read from
the agent's own file and never from the settings it inherits, so a desktop is on only where
somebody wrote so."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from my_agent_crew.config_desktop import (
    COMPUTER_MODES,
    COMPUTER_OFF,
    COMPUTER_ON,
    DesktopSettings,
)

# An application's name or its bundle id is short; a longer entry is a mistake in the file.
APP_CHARS = 200


def desktop_of(raw: dict[str, Any], agent_id: str, base: DesktopSettings) -> DesktopSettings:
    return replace(base, mode=_mode(raw, agent_id), apps=_apps(raw, agent_id))


def _mode(raw: dict[str, Any], agent_id: str) -> str:
    value = raw.get("computer", COMPUTER_OFF)
    known = f"agent {agent_id}: computer must be {COMPUTER_OFF} or {COMPUTER_ON}"
    # YAML reads a bare `off`, `no` or `false` as this, and each of them means what it says.
    if value is None or value is False:
        return COMPUTER_OFF
    if value is True:
        # A bare `on`, `yes` or `true`. The screen and the keyboard of the machine's owner are
        # handed over by the word itself and by nothing YAML made of another word.
        raise ValueError(
            f'{known}, written as a text: put "{COMPUTER_ON}" in quotes, since YAML reads a'
            " bare on, yes or true as a switch and not as that word"
        )
    if not isinstance(value, str) or value not in COMPUTER_MODES:
        raise ValueError(known)
    return value


def _apps(raw: dict[str, Any], agent_id: str) -> tuple[str, ...]:
    refusal = ValueError(
        f"agent {agent_id}: computer_apps must be a list of application names or bundle ids,"
        " such as Notes or com.apple.Notes"
    )
    value = raw.get("computer_apps")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise refusal
    apps: list[str] = []
    for entry in value:
        if not isinstance(entry, str) or not _one_name(entry.strip()):
            raise refusal
        if entry.strip() not in apps:
            apps.append(entry.strip())
    return tuple(apps)


def _one_name(text: str) -> bool:
    """A name that is there, fits and is one line: it is told to the agent and to the helper."""
    return 0 < len(text) <= APP_CHARS and text.isprintable()
