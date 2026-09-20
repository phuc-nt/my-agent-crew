"""A short recap of the conversation an agent just left behind.

Written in the background when the next conversation opens on the same channel, so the
new turn starts with "what we did last time" instead of an empty slate. Job runs are
skipped: they open a fresh conversation on every tick, and their output is the delivery,
not a thread worth remembering."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from my_agent_crew.llm.types import Completion, Message
from my_agent_crew.store import Store, StoredMessage
from my_agent_crew.texts import SUMMARY_PROMPT, SUMMARY_TRANSCRIPT_LINE

if TYPE_CHECKING:  # avoids a cycle: the loop imports memory sections, not the other way
    from my_agent_crew.agent.loop import AgentDeps

logger = logging.getLogger(__name__)

MAX_SUMMARY_CHARS = 600
MAX_TRANSCRIPT_CHARS = 12000
JOB_SOURCE_PREFIX = "job:"


def transcript_text(history: list[StoredMessage], limit: int = MAX_TRANSCRIPT_CHARS) -> str:
    """User and assistant text only, newest kept when the transcript is too long."""
    lines = [
        SUMMARY_TRANSCRIPT_LINE.format(role=m.message.role, text=m.message.content.strip())
        for m in history
        if m.message.role in ("user", "assistant") and m.message.content.strip()
    ]
    text = "\n".join(lines)
    return text[-limit:] if len(text) > limit else text


def _is_job_conversation(store: Store, conv_id: str) -> bool:
    run = store.runs.latest_for_conversation(conv_id)
    return run is not None and run.source.startswith(JOB_SOURCE_PREFIX)


async def summarize_conversation(deps: AgentDeps, conv_id: str, force: bool = False) -> str:
    """Write `conversations.summary` and return it; empty string when skipped."""
    conv = deps.store.get(conv_id)
    if conv.summary and not force:
        return conv.summary
    if _is_job_conversation(deps.store, conv_id):
        return ""
    history = deps.store.history(conv_id)
    if not any(m.message.role == "assistant" and m.message.content.strip() for m in history):
        return ""
    transcript = transcript_text(history)
    if not transcript:
        return ""
    prompt = Message(role="user", content=SUMMARY_PROMPT.format(transcript=transcript))
    completion: Completion | None = None
    async for item in deps.chain.stream([prompt], []):
        if isinstance(item, Completion):
            completion = item
    if completion is None:
        return ""
    summary = " ".join(completion.message.content.split())[:MAX_SUMMARY_CHARS]
    if not summary:
        return ""
    deps.store.update(conv_id, summary=summary)
    deps.store.add_spend(conv_id, completion.usage.cost_usd)
    return summary


def schedule_summary(keep: object, deps: AgentDeps, conv_id: str) -> None:
    """Fire-and-forget summary for a conversation that was just replaced.

    `keep` is `Scheduler.keep` (or any callable holding a task reference) so the task is
    not garbage-collected mid-flight. Must be called from the event loop: a recap costs a
    model call, far too slow to run inline on the request that opened the conversation."""

    async def run() -> None:
        try:
            await summarize_conversation(deps, conv_id)
        except Exception:  # a failed summary must never break the new conversation
            logger.exception("summary failed for conversation %s", conv_id)

    task = asyncio.create_task(run())
    if callable(keep):
        keep(task)
