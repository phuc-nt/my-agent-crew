"""Web Push: the crew tells a phone or a browser that something waits for the person, with
no app store and no third party beyond the push service the browser itself uses."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from my_agent_crew.webpush.store import PushStore


@cache
def push_store(home: Path) -> PushStore:
    """One store per home, so the routes and the notifier share its lock."""
    return PushStore(home)
