"""A server that stops under a turn, and the one started next on the same database.

`served` (`conftest.py`) builds every app of a test on one store, so the second app a test
builds is the next process: its hub settles what the first one left open as it is made.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import replace

from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store.runs import RunRecord
from my_agent_crew.turn_resume import resume_cut_turns
from tests.queue_helpers import Served, SlowTool, settle_loop, until


async def go_down(runtime: Runtime) -> None:
    """What the app's shutdown does to the turns under way (`server/app.py`)."""
    runtime.hub.going_down = True
    await runtime.drain.stop()
    await runtime.inbound.host.stop()
    await runtime.stop_channel()
    await runtime.scheduler.stop()
    await settle_loop()  # the scheduler cancels its tasks without waiting for them


async def cut_mid_tool(
    app: Served, tool: SlowTool | None = None, text: str = "làm đi"
) -> RunRecord:
    """Sends `text`, waits until the turn's tool is running, and takes the server down under
    it. Returns the turn's run as the store is left with it."""
    sender = asyncio.create_task(app.client.post(app.messages, json={"text": text}))
    await asyncio.wait_for((tool or app.slow).started.wait(), 2)
    await go_down(app.runtime)
    await asyncio.wait_for(sender, 2)
    return stored_run(app)


def next_server(
    served: Callable[..., Served], before: Served, script: Sequence, **kwargs
) -> Served:
    """The server started after `before` went down, on the conversation it was answering."""
    return replace(served(script, **kwargs), conv=before.conv)


def stored_run(app: Served, conv_id: str | None = None) -> RunRecord:
    run = app.runtime.store.runs.latest_for_conversation(conv_id or app.conv.id)
    assert run is not None
    return run


async def carried_on(app: Served) -> RunRecord:
    """Takes up what the restart cut, waits for the conversation to fall idle, and returns
    its run as stored."""
    resume_cut_turns(app.runtime)
    return await idle(app)


async def idle(app: Served, conv_id: str | None = None) -> RunRecord:
    conv_id = conv_id or app.conv.id
    await until(lambda: not app.runtime.hub.busy.busy(conv_id))
    await settle_loop()
    return stored_run(app, conv_id)


def history(app: Served, conv_id: str | None = None) -> list[tuple[str, str]]:
    stored = app.runtime.store.history(conv_id or app.conv.id)
    return [(m.message.role, m.message.content) for m in stored]
