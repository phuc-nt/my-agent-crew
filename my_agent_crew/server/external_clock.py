"""The scheduler's clock, or, when the host keeps it (`hosting.external_clock`), the one
part of it the server still runs: approvals left waiting lapse on time either way."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping

from my_agent_crew.agent.approval_expiry import expire_overdue
from my_agent_crew.hosting import external_clock
from my_agent_crew.scheduler.runner import TICK_SECONDS
from my_agent_crew.server.runtime import Runtime

logger = logging.getLogger(__name__)


async def approvals_loop(runtime: Runtime, seconds: float = TICK_SECONDS) -> None:
    while True:
        try:
            await expire_overdue(runtime.agents, runtime.hub, runtime.deliver)
        except Exception:  # one bad lapse must not stop the next
            logger.exception("approval expiry failed")
        await asyncio.sleep(seconds)


def start_clock(runtime: Runtime, env: Mapping[str, str]) -> asyncio.Task[None] | None:
    """Starts the scheduler, or, with the clock outside, only the lapsing of approvals; the
    task returned is the caller's to cancel."""
    if not external_clock(env):
        runtime.scheduler.start()
        return None
    logger.info("scheduler: the clock is external; a job runs when the host says")
    return asyncio.create_task(approvals_loop(runtime))
