"""Grouping the tool calls in one assistant message into batches that run together.

Most tools are settled one at a time: they touch the workspace, and running them
concurrently would make the order of writes depend on timing. A tool marked `parallel`
spends its turn waiting on something else, so a message asking for several of them runs
them at once — the difference between four delegated tasks costing four turns' worth of
wall clock and costing one.

A call that first needs a person's decision is never batched: the turn stops there until
they answer, so it has to be settled on its own.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from my_agent_crew.llm.types import ToolCall
from my_agent_crew.tools.registry import ToolRegistry

# One message asking for more than this many parallel tasks is capped rather than fanned
# out; past a handful it is a runaway, not a plan.
MAX_PARALLEL_CALLS = 8


def split_batches(
    calls: Sequence[ToolCall], tools: ToolRegistry, runs_now: Callable[[ToolCall], bool]
) -> list[list[ToolCall]]:
    """Consecutive parallel calls that `runs_now` says need no decision become one batch;
    every other call is a batch of one, leaving the sequential path exactly as it was."""
    batches: list[list[ToolCall]] = []
    open_batch = False
    for call in calls:
        tool = tools.get(call.name)
        parallel = tool is not None and tool.parallel and runs_now(call)
        if parallel and open_batch and len(batches[-1]) < MAX_PARALLEL_CALLS:
            batches[-1].append(call)
            continue
        batches.append([call])
        open_batch = parallel
    return batches
