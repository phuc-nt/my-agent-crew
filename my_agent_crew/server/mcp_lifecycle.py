"""When the crew talks to its MCP servers without being asked: once as it starts, and
again later for the ones that did not answer.

Starting waits for them only so long. A server that is slow or down must not keep the crew
from answering its owner, so what has not connected by then is left to the loop below,
which tries at growing intervals and at once when a key changes. A server that wants a
sign-in is not retried: only the owner can give it one.
"""

from __future__ import annotations

import asyncio
import logging

from my_agent_crew.server.runtime import Runtime

logger = logging.getLogger(__name__)

STARTUP_SECONDS = 10.0
FIRST_RETRY_SECONDS = 30.0
LONGEST_RETRY_SECONDS = 600.0


async def connect_at_start(rt: Runtime, limit: float = STARTUP_SECONDS) -> None:
    if not rt.mcp.links:
        return
    try:
        await asyncio.wait_for(rt.mcp.connect(), limit)
    except TimeoutError:
        late = ", ".join(rt.mcp.waiting())
        logger.warning("MCP servers not connected after %gs, trying later: %s", limit, late)
    rt.mcp.attach(rt.agents)


async def retry_loop(
    rt: Runtime, first: float = FIRST_RETRY_SECONDS, longest: float = LONGEST_RETRY_SECONDS
) -> None:
    """Try the servers that are down, for as long as the crew runs."""
    wake, delay = rt.mcp.wake, first
    while True:
        try:
            await asyncio.wait_for(wake.wait(), delay)
        except TimeoutError:
            asked = False
        else:
            asked = True
            wake.clear()
        down = rt.mcp.waiting()
        if not down:
            delay = first
            continue
        await rt.mcp.connect(down)
        rt.mcp.attach(rt.agents)
        # The wait grows only while a server stays down, and one someone cut short says
        # nothing of how long that has been.
        growing = bool(rt.mcp.waiting()) and not asked
        delay = min(delay * 2, longest) if growing else first
