"""The browser the crew owns: whether the machine has one at all, which Chromium it starts and
how long an unused one stays up. An agent's own file says whether that agent may read pages
or also act on them (`agents/profile_browser.py`); nothing here turns it on for anyone.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from my_agent_crew.config_parse import as_bool
from my_agent_crew.texts_browser import DEFAULT_ASK_WORDS

# What an agent's `browser` key may say, from nothing to the most.
BROWSER_OFF, BROWSER_READ, BROWSER_ACT = "off", "read", "act"
BROWSER_MODES = (BROWSER_OFF, BROWSER_READ, BROWSER_ACT)
# The Chromium Playwright ships, pinned with the package, or the Chrome installed here.
CHANNELS = ("chromium", "chrome")


@dataclass(frozen=True)
class BrowserSettings:
    enabled: bool = False
    channel: str = "chromium"
    # An agent's browser nobody used for this long is stopped; the next call starts it again.
    idle_minutes: int = 10
    # Tabs one agent's browser holds at once, over all its conversations.
    max_tabs: int = 5
    # Element names that stop an action for a person. Empty turns this soft guard off; the
    # hard refusals (private addresses, password fields) are code and stay.
    ask_patterns: tuple[str, ...] = DEFAULT_ASK_WORDS
    # The two below are set only by an agent's own file.
    mode: str = BROWSER_OFF
    # Hosts the agent goes to without asking, and outside which it always asks. Empty means
    # no list: every navigation is asked for like any other change.
    hosts: tuple[str, ...] = ()

    @property
    def reads(self) -> bool:
        return self.enabled and self.mode != BROWSER_OFF

    @property
    def acts(self) -> bool:
        return self.enabled and self.mode == BROWSER_ACT


def browser_settings(env: Mapping[str, str], file_values: Mapping[str, object]) -> BrowserSettings:
    channel = str(env.get("MY_AGENT_BROWSER_CHANNEL") or file_values.get("browser_channel", ""))
    channel = channel.strip() or CHANNELS[0]
    if channel not in CHANNELS:
        raise ValueError(f"browser_channel must be {' or '.join(CHANNELS)}, got {channel!r}")
    idle = int(
        env.get("MY_AGENT_BROWSER_IDLE_MINUTES") or file_values.get("browser_idle_minutes", 10)
    )
    tabs = int(env.get("MY_AGENT_BROWSER_MAX_TABS") or file_values.get("browser_max_tabs", 5))
    if min(idle, tabs) < 1:
        raise ValueError("browser_idle_minutes and browser_max_tabs must be >= 1")
    return BrowserSettings(
        enabled=as_bool(
            env.get("MY_AGENT_BROWSER_ENABLED", file_values.get("browser_enabled", False))
        ),
        channel=channel,
        idle_minutes=idle,
        max_tabs=tabs,
        ask_patterns=_ask_patterns(
            env.get("MY_AGENT_BROWSER_ASK_PATTERNS"), file_values.get("browser_ask_patterns")
        ),
    )


def _ask_patterns(from_env: str | None, from_file: object) -> tuple[str, ...]:
    """An empty env value or an empty yaml list turns the guard off on purpose; only an
    absent setting falls back to the defaults."""
    if from_env is not None:
        return tuple(p.strip() for p in from_env.split(";") if p.strip())
    if isinstance(from_file, Sequence) and not isinstance(from_file, str):
        return tuple(str(p).strip() for p in from_file if str(p).strip())
    return DEFAULT_ASK_WORDS
