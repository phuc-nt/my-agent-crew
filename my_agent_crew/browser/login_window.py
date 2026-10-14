"""One window a person signs in through, while it is open: the Chromium it is, the proxy it
goes out through, until when it stays, and what it was last seen to be signed in to.
`login.py` opens one and decides when it closes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from my_agent_crew.browser.launch import shut_down
from my_agent_crew.browser.logins import read, remember
from my_agent_crew.browser.proxy import FilteringProxy


@dataclass
class Window:
    agent_id: str
    context: Any
    proxy: FilteringProxy
    until: datetime
    timer: asyncio.Task[None] | None = None
    # What it was last seen to hold: a browser the person quits cannot be asked afterwards.
    held: dict[str, float] | None = None

    async def look(self) -> None:
        """Ask the window what it holds; one that tells nothing keeps what was seen before."""
        seen = await read(self.context)
        self.held = self.held if seen is None else seen

    async def close(self, profile: Path, *, gone: bool = False) -> None:
        """Write down where the window is signed in and close it. One that is `gone`, its
        driver with it, is asked nothing: what it was last seen to hold is written, and its
        proxy is stopped as any other's."""
        if self.timer is not None:
            self.timer.cancel()
        try:
            await remember(None if gone else self.context, profile, self.held)
            if not gone:
                await shut_down(self.context)
        finally:
            await self.proxy.stop()
