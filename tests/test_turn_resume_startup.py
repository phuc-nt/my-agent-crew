"""Which cut turns a starting server takes up, and that the served app does it by itself
(`turn_resume.py`, the lifespan in `server/app.py`).

A run handed back by the hub is carried on only while doing so is still what the
conversation needs: one left alone stays closed as interrupted and asks no model."""

from __future__ import annotations

import asyncio

import httpx

from my_agent_crew import texts
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import Message, ToolCall
from my_agent_crew.server import create_app
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store.runs import DONE, FAILED, RUNNING, RunRecord
from my_agent_crew.turn_resume import resume_cut_turns
from tests.queue_helpers import GatedProvider, SlowTool, until
from tests.restart_helpers import history, idle, next_server, stored_run
from tests.test_server_api import parse_sse

SLOW = ToolCall("c1", "slow", {})
GUARDED = ToolCall("g1", "guarded", {})


def left_working(store, run_id: str, conv_id: str, started: str = "08:00") -> RunRecord:
    """A row as a process that died mid-turn leaves it."""
    run = RunRecord(run_id, "default", conv_id, "chat", "t", RUNNING, f"2026-10-06T{started}:00")
    store.runs.save(run)
    return run


def interrupted(store, run_id: str) -> bool:
    run = store.runs.get(run_id)
    return (run.status, run.summary) == (FAILED, "interrupted")


async def test_a_turn_that_had_asked_a_person_waits_for_them_and_is_not_started_again(served):
    """The server died after the request for a decision was written and before the run was
    marked as paused. The decision carries the turn on; starting it here would ask twice."""
    first = served([])
    store, conv = first.runtime.store, first.conv
    store.append(conv.id, Message(role="user", content="ghi đi"))
    store.append(conv.id, Message(role="assistant", content="", tool_calls=(GUARDED,)))
    approval = store.approvals.create(conv.id, 2, GUARDED)
    left_working(store, "r1", conv.id)

    second = next_server(served, first, [completion("đã ghi")])

    assert [run.id for run in second.runtime.hub.cut] == ["r1"]
    assert resume_cut_turns(second.runtime) == []
    assert interrupted(store, "r1") and second.provider.requests == []
    assert store.approvals.pending(conv.id).id == approval.id
    # The person's answer is what moves it, exactly as on a server that never stopped.
    decided = await second.client.post(
        f"{second.detail}/approvals/{approval.id}", json={"approve": True}
    )
    assert parse_sse(decided.text)[-1]["type"] == "done"
    assert second.guarded.runs == 1 and history(second)[-1] == ("assistant", "đã ghi")


async def test_a_run_whose_conversation_went_on_without_it_is_left_closed(served):
    """An older working row under a turn that ended since: the conversation has its answer."""
    first = served([])
    store, conv = first.runtime.store, first.conv
    left_working(store, "old", conv.id, "08:00")
    ended = RunRecord("new", "default", conv.id, "chat", "t", DONE, "2026-10-06T09:00:00")
    store.runs.save(ended)

    second = next_server(served, first, [completion("không được hỏi")])

    assert [run.id for run in second.runtime.hub.cut] == ["old"]
    assert resume_cut_turns(second.runtime) == []
    assert interrupted(store, "old") and store.runs.get("new").status == DONE
    assert second.provider.requests == [] and not second.runtime.hub.busy.busy(conv.id)


async def test_a_run_whose_conversation_was_deleted_is_left_closed(served):
    first = served([])
    left_working(first.runtime.store, "r1", "gone")

    second = next_server(served, first, [completion("không được hỏi")])

    assert [run.id for run in second.runtime.hub.cut] == ["r1"]
    assert resume_cut_turns(second.runtime) == []
    assert interrupted(second.runtime.store, "r1") and second.provider.requests == []


async def test_the_cut_runs_are_taken_up_once_per_start(served):
    """Asking again finds nothing: the list is emptied as it is read."""
    first = served([])
    store, conv = first.runtime.store, first.conv
    store.append(conv.id, Message(role="user", content="chào"))
    left_working(store, "r1", conv.id)

    second = next_server(served, first, [completion("xin chào")])

    assert [run.id for run in resume_cut_turns(second.runtime)] == ["r1"]
    assert resume_cut_turns(second.runtime) == [] and second.runtime.hub.cut == []
    assert (await idle(second)).status == DONE
    assert len(second.provider.requests) == 1


def scheduled(deps_factory, script) -> tuple[Runtime, GatedProvider, SlowTool]:
    """A runtime for an app that owns its lifespan, as the live server does."""
    provider, slow = GatedProvider(script), SlowTool()
    deps = deps_factory(providers={"scripted": provider}, extra_tools=[slow.tool])
    return Runtime.single(deps), provider, slow


async def test_the_served_app_leaves_a_turn_its_stop_cut_and_carries_it_on_at_the_next_start(
    deps_factory,
):
    first, _, slow = scheduled(deps_factory, [completion(tool_calls=[SLOW])])
    app = create_app(first, schedule=True)
    conv = first.store.create("Việc thử", agent_id=first.default.agent.id)
    url = f"/api/conversations/{conv.id}/messages"
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
            sender = asyncio.create_task(client.post(url, json={"text": "làm đi"}))
            await asyncio.wait_for(slow.started.wait(), 2)
    await asyncio.wait_for(sender, 2)
    cut = first.store.runs.latest_for_conversation(conv.id)
    assert cut is not None and (cut.status, cut.finished_at) == (RUNNING, None)

    second, provider, again = scheduled(deps_factory, [completion("đã kiểm tra")])
    app = create_app(second, schedule=True)
    async with app.router.lifespan_context(app):
        await until(lambda: not second.hub.busy.busy(conv.id) and len(provider.requests) == 1)
        run = second.store.runs.latest_for_conversation(conv.id)

    assert run is not None and (run.id, run.status, run.resumed) == (cut.id, DONE, True)
    assert again.runs == 0
    stored = [(m.message.role, m.message.content) for m in second.store.history(conv.id)]
    assert stored[-2:] == [("tool", texts.RESTART_CUT_TOOL), ("assistant", "đã kiểm tra")]


async def test_an_app_that_schedules_nothing_takes_nothing_up(served):
    """What tests and embedders build: no bot, no jobs, and no turn begun on its own."""
    first = served([])
    store, conv = first.runtime.store, first.conv
    store.append(conv.id, Message(role="user", content="chào"))
    left_working(store, "r1", conv.id)

    second = next_server(served, first, [completion("không được hỏi")])
    app = create_app(second.runtime, schedule=False)
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.05)

    assert interrupted(store, "r1") and second.provider.requests == []
    assert stored_run(second).id == "r1"
