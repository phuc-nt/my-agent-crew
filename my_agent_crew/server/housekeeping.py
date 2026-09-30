"""Background upkeep that is not tied to any request: today, removing spill files that
have outlived their usefulness. A conversation that is never deleted would otherwise keep
the full text of every long tool result forever."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from my_agent_crew.tools.output_spill import sweep

logger = logging.getLogger(__name__)
SWEEP_INTERVAL_SECONDS = 86400


async def sweep_loop(home: Path, interval_seconds: float = SWEEP_INTERVAL_SECONDS) -> None:
    """Sweeps once straight away (a server that restarts more often than daily would never
    sweep otherwise), then every `interval_seconds`, until cancelled. The walk touches the
    disk, so it runs off the event loop; a failed sweep is logged and the next one still runs."""
    while True:
        try:
            removed = await asyncio.to_thread(sweep, home)
        except Exception:
            logger.exception("spill sweep failed")
        else:
            if removed:
                logger.info("spill sweep removed %d old file(s)", removed)
        await asyncio.sleep(interval_seconds)
