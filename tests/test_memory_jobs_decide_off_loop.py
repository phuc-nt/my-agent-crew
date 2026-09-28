"""A scheduled memory job writes by the web's one-decision-at-a-time rule, and waits for a
decision still writing there without holding up the event loop that serves everyone else."""

from __future__ import annotations

import asyncio
import json
import os
import threading

import pytest

from my_agent_crew.activity import ActivityHub
from my_agent_crew.llm.fake import completion
from my_agent_crew.memory import agent_store, proposals_apply
from my_agent_crew.memory.consolidate import consolidate_memory
from my_agent_crew.memory.wiki_compile import compile_wiki
from my_agent_crew.store.memory_proposals import APPROVED

PAGES = json.dumps(
    [
        {
            "title": "Hạn Eco",
            "kind": "entities",
            "body": "Hạn nộp hồ sơ là thứ tư, đã dời một lần từ thứ hai tuần trước.",
            "sources": ["note:2026-09-19"],
        }
    ],
    ensure_ascii=False,
)


async def released_by_the_loop(deps, job) -> bool:
    """Run `job` while a decision holds the lock, and release it from the event loop once
    the job's proposal is listed. A job that waits on the loop itself stops the loop, and
    only a thread's fallback release lets it go on."""
    released: list[str] = []

    def release(by: str) -> None:
        if not released:
            released.append(by)
            proposals_apply._deciding.release()

    proposals_apply._deciding.acquire()
    fallback = threading.Timer(2.0, release, args=("thread",))
    fallback.start()
    try:
        task = asyncio.create_task(job)
        while not deps.store.proposals.list(status=None) and not task.done():
            await asyncio.sleep(0.005)
        release("loop")
        await task
    finally:
        fallback.cancel()
        release("cleanup")
    return released == ["loop"]


@pytest.fixture
def hub(store) -> ActivityHub:
    return ActivityHub(store)


async def test_an_autonomous_rewrite_waits_for_a_decision_off_the_event_loop(deps_factory, hub):
    deps = deps_factory(script=[completion("- Sếp thích trà.")], autonomous_default=True)
    memory = deps.agent.memory_file
    agent_store.write_memory_md(memory, "- Cũ.")
    agent_store.write_note(deps.agent.memory_dir, "2026-09-19", "Sếp thích trà.")
    stamp = memory.stat().st_mtime + 10
    os.utime(deps.agent.memory_dir / "2026-09-19.md", (stamp, stamp))

    assert await released_by_the_loop(deps, consolidate_memory(deps, hub))
    assert [p.status for p in deps.store.proposals.list(status=None)] == [APPROVED]


async def test_an_autonomous_compile_waits_for_a_decision_off_the_event_loop(deps_factory, hub):
    deps = deps_factory(script=[completion(PAGES)], autonomous_default=True)
    agent_store.write_note(deps.agent.memory_dir, "2026-09-19", "Hạn Eco là thứ tư.")

    assert await released_by_the_loop(deps, compile_wiki(deps, hub))
    assert [p.status for p in deps.store.proposals.list(status=None)] == [APPROVED]
