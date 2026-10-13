"""The crew's browsers as the server holds them: whether the machine has one to start, the
pool the agents' tools start theirs in, and what becomes of an agent's browser when the
agent is switched off it or leaves the crew.

The folder the browsers keep their logins in is closed to every file tool and to every
sandboxed command whether or not a browser is ever started (`tools/private_paths.py`,
`tools/shell_sandbox.py`): a machine that turned the browser off yesterday still holds what
was signed in to the day before.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from my_agent_crew.browser.install import NO_BROWSER, NO_PACKAGE, Installed, installed
from my_agent_crew.browser.pool import BrowserPool
from my_agent_crew.browser.tools import build_browser_tools
from my_agent_crew.config_browser import CHANNELS, BrowserSettings, browser_root, profile_dir
from my_agent_crew.tools.private_paths import keep_private
from my_agent_crew.tools.registry import Tool

if TYPE_CHECKING:
    from my_agent_crew.agents import AgentProfile
    from my_agent_crew.config import Settings

logger = logging.getLogger(__name__)

# How often the unused browsers and the cold tabs are looked for.
REAP_SECONDS = 60.0
# What to run for what is missing. The Chrome of the machine is its owner's to install.
INSTALL = {NO_PACKAGE: "uv sync", NO_BROWSER: "uv run playwright install chromium"}
MISSING = {NO_PACKAGE: "the playwright package", NO_BROWSER: "the browser itself"}


@dataclass
class Browsers:
    root: Path
    # The machine's settings: an agent's own mode and hosts are in its profile.
    settings: BrowserSettings
    found: Installed
    # None where the machine's file leaves the browser off, or where there is none to start:
    # no agent is given a browser tool then, whatever its own file asks for.
    pool: BrowserPool | None = None

    @property
    def install_command(self) -> str:
        if self.found.missing == NO_BROWSER and self.settings.channel != CHANNELS[0]:
            return ""
        return INSTALL.get(self.found.missing, "")

    def status(self, agent_ids: Iterable[str]) -> dict[str, Any]:
        """What the machine has, and whose browser is up now. Read when the server started:
        a browser installed since is found at the next start."""
        pool = self.pool
        return {
            "enabled": self.settings.enabled,
            "channel": self.settings.channel,
            "installed": self.found.ok,
            "version": self.found.version,
            "missing": self.found.missing,
            "install_command": self.install_command,
            "running": sorted(a for a in agent_ids if pool is not None and pool.running(a)),
        }

    async def stop(self, agent_id: str) -> bool:
        """Stop the agent's browser now. What it is signed in to stays in its profile, and
        its next call starts it again. Whether there was one for this call to stop."""
        return self.pool is not None and await self.pool.stop(agent_id)

    async def forget(self, agent_id: str) -> None:
        """An agent left the crew: its browser is stopped and the folder its logins were kept
        in goes with it. An agent later given the id would otherwise wake up signed in as the
        one that was removed."""
        folder = profile_dir(self.root, agent_id)
        await self.stop(agent_id)
        try:
            await asyncio.to_thread(shutil.rmtree, folder)
        except FileNotFoundError:
            pass  # it never opened a page
        except OSError as error:
            logger.warning("browser profile of removed agent %s stays: %s", agent_id, error)


def build_browsers(settings: Settings, env: Mapping[str, str]) -> Browsers:
    """The browsers of a crew whose home is `settings.home`. The folder is closed first and
    in every case; a pool is made only where the machine's file turns the browser on and the
    browser it names is here. Nothing is started: an agent's first call does that."""
    root, own = browser_root(settings.home), settings.browser
    keep_private(root)
    browsers = Browsers(root, own, installed(own.channel, env))
    if own.enabled and browsers.found.ok:
        browsers.pool = BrowserPool(root, own)
    elif own.enabled:
        command = browsers.install_command
        logger.warning(
            "browser_enabled is set but %s is missing: no agent is given a browser tool%s",
            MISSING[browsers.found.missing],
            f" (run: {command})" if command else "",
        )
    return browsers


def browser_tools_of(
    pool: BrowserPool | None, profile: AgentProfile, limit: int, vision: Any = None
) -> list[Tool]:
    """The browser tools the agent's own file asks for; none where there is no pool."""
    return build_browser_tools(
        pool,
        profile.id,
        profile.settings.browser,
        profile.workspace,
        limit,
        vision=vision,
        write_paths=profile.settings.write_paths,
    )


async def reap_loop(pool: BrowserPool, interval_seconds: float = REAP_SECONDS) -> None:
    """Stops the browsers nobody used for a while and closes the cold tabs of the others,
    every `interval_seconds` until cancelled. A round that failed is logged and the next one
    still runs."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            stopped = await pool.reap()
        except Exception:
            logger.exception("browser reap failed")
        else:
            for agent_id in stopped:
                logger.info("browser of agent %s stopped: nobody used it", agent_id)
