"""A restart between a pause and its decision: the paused run is held again and continued,
and a paused run nothing can continue any more is closed instead of waiting forever."""

from fastapi.testclient import TestClient

from my_agent_crew.activity import ActivityHub, tracked
from my_agent_crew.activity.steps import apply_event
from my_agent_crew.agent.events import ToolCallEvent, ToolResultEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.resume import resolve_approval
from my_agent_crew.config import Route, load_settings
from my_agent_crew.server import build_runtime, create_app
from my_agent_crew.store.runs import AWAITING, DONE, FAILED, RUNNING, RunRecord
from tests.conftest import collect

PAUSING = '/tool shell_run {"command": "echo 1"}'


async def pause(deps, hub: ActivityHub, conv_id: str) -> list:
    return await collect(
        tracked(hub, run_turn(deps, conv_id, PAUSING), "default", "chat", "t", conv_id)
    )


async def test_the_decision_after_a_restart_continues_the_run_that_paused(deps_factory):
    """Before, the decision started a second run and the paused one stayed waiting for
    good, counted as live on every screen that counts runs."""
    deps = deps_factory(routes=(Route("fake", "echo"),))
    conv = deps.store.create()
    paused = await pause(deps, ActivityHub(deps.store), conv.id)

    # What the next process builds on the same database.
    hub = ActivityHub(deps.store)
    [held] = hub.live()
    assert held.status == AWAITING and held.conversation_id == conv.id

    resumed = resolve_approval(deps, conv.id, paused[-1].approval_id, True)
    await collect(tracked(hub, resumed, "default", "chat", "t", conv.id))
    assert hub.live() == []
    [run] = deps.store.runs.recent(conversation_ids=[conv.id])
    assert run.id == held.id and run.status == DONE
    tool = next(step for step in run.steps if step["kind"] == "tool")
    assert tool["ok"] is True and tool["duration_ms"] >= 0


async def test_a_paused_run_whose_request_is_gone_is_closed_at_restart(deps_factory):
    """Its request was decided while no process held the run, or it never had one to
    wait on: nothing will ever continue it, so it must stop counting as live."""
    deps = deps_factory(routes=(Route("fake", "echo"),))
    conv = deps.store.create()
    await pause(deps, ActivityHub(deps.store), conv.id)
    [stale] = deps.store.runs.recent(conversation_ids=[conv.id])
    deps.store.approvals.resolve(deps.store.approvals.pending(conv.id).id, approve=True)
    orphan = RunRecord("orphan", "default", None, "chat", "t", AWAITING, "2026-09-19T08:00:00")
    deps.store.runs.save(orphan)

    hub = ActivityHub(deps.store)

    assert hub.live() == []
    for run_id in (stale.id, "orphan"):
        closed = deps.store.runs.get(run_id)
        assert closed.status == FAILED and closed.summary == "interrupted"
        assert closed.finished_at is not None


async def test_only_the_newest_paused_run_of_a_conversation_is_held(deps_factory):
    """An older paused row of the same conversation is what a restart before this fix
    left behind; holding it too would let the decision continue the wrong run."""
    deps = deps_factory(routes=(Route("fake", "echo"),))
    conv = deps.store.create()
    first = ActivityHub(deps.store)
    await pause(deps, first, conv.id)
    [newest] = first.live()
    older = RunRecord("older", "default", conv.id, "chat", "t", AWAITING, "2026-09-01T08:00:00")
    deps.store.runs.save(older)

    hub = ActivityHub(deps.store)

    assert [run.id for run in hub.live()] == [newest.id]
    assert deps.store.runs.get("older").status == FAILED


def test_a_step_resumed_after_a_reboot_never_reads_a_negative_duration():
    """The step was opened on the previous boot's clock, which a reboot starts again."""
    run = RunRecord("r1", "default", "c1", "chat", "t", RUNNING, "2026-09-19T08:00:00")
    apply_event(run, ToolCallEvent("t1", "shell_run", {"command": "ls"}), 900_000.0)
    apply_event(run, ToolResultEvent("t1", "shell_run", True, "a.txt"), 12.0)
    assert run.steps[-1]["duration_ms"] == 0


def test_deleting_a_conversation_closes_the_run_paused_in_it(tmp_path):
    """The delete takes the pending request with it, so the pause could never end."""
    env = {"MY_AGENT_HOME": str(tmp_path), "MY_AGENT_ROUTES": "fake:echo"}
    runtime = build_runtime(load_settings(env=env))
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        conv = client.post("/api/conversations", json={}).json()
        text = '/tool workspace_write {"path": "x.txt", "content": "1"}'
        client.post(f"/api/conversations/{conv['id']}/messages", json={"text": text})
        [paused] = runtime.hub.live()
        assert paused.status == AWAITING
        assert client.delete(f"/api/conversations/{conv['id']}").status_code == 204
    assert runtime.hub.live() == []
    closed = runtime.store.runs.get(paused.id)
    assert closed.status == FAILED and closed.summary == "interrupted"
