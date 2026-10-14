"""One agent's browser while it is up: the context it runs in, the proxy it goes out through,
its tabs and the files it was sent. `pool.py` starts one and stops it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from my_agent_crew.browser.downloads import Downloads
from my_agent_crew.browser.launch import shut_down
from my_agent_crew.browser.logins import remember
from my_agent_crew.browser.proxy import FilteringProxy
from my_agent_crew.browser.tabs import Tabs


class Reserved(RuntimeError):
    """The agent's profile is in a person's hands: no browser is started on it."""


@dataclass
class Session:
    agent_id: str
    context: Any
    proxy: FilteringProxy
    tabs: Tabs
    used: float
    busy: int = 0
    downloads: Downloads | None = None
    profile: Path | None = None

    async def close(self) -> None:
        # Where it is signed in is read while it can still say (`logins.py`).
        await remember(self.context, self.profile)
        await shut_down(self.context)
        await self.proxy.stop()
