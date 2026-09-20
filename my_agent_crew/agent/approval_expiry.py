"""Closing approval requests nobody answered.

A paused turn holds its conversation, and for a job its channel, until someone decides.
When the deadline passes the request is closed as expired, the loop resumes with the
tool refused (the model reads it as a denial) and the answer is delivered as usual, so
a night job that hit a guard still reports in the morning instead of waiting silently.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime

from my_agent_crew.activity import ActivityHub, tracked
from my_agent_crew.agent.loop import AgentDeps, run_turn
from my_agent_crew.agent.turn_context import conversation_source
from my_agent_crew.store.approvals import EXPIRED
from my_agent_crew.store.models import IDLE

logger = logging.getLogger(__name__)
Deliver = Callable[[str, str], Awaitable[bool]]


async def expire_overdue(
    agents: Mapping[str, AgentDeps],
    hub: ActivityHub,
    deliver: Deliver | None = None,
    now: datetime | None = None,
) -> list[str]:
    """Closes every overdue request and finishes its turn; returns the ids closed. One
    failing turn is logged and the sweep goes on, the way a broken job does not stop
    the scheduler."""
    if not agents:
        return []
    store = next(iter(agents.values())).store
    closed: list[str] = []
    for approval in store.approvals.overdue(now or datetime.now(UTC)):
        store.approvals.resolve(approval.id, approve=False, status=EXPIRED)
        conv = store.update(approval.conversation_id, status=IDLE)
        deps = agents.get(conv.agent_id) or next(iter(agents.values()))
        logger.info(
            "approval %s for %s expired (conv %s)", approval.id, approval.tool_name, conv.id
        )
        source = conversation_source(store, conv.id)
        events = tracked(
            hub,
            run_turn(deps, conv.id, None, source=source),
            deps.agent.id,
            source,
            conv.title,
            conv.id,
        )
        try:
            async for _ in events:
                pass
            if deliver is not None:
                await deliver(deps.agent.id, conv.id)
        except Exception:
            logger.exception("approval %s: resuming after expiry failed", approval.id)
        closed.append(approval.id)
    return closed
