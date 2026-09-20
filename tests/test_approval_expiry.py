"""An approval nobody answers closes as expired: the tool is refused, the turn finishes,
the answer is delivered, and the scheduler runs the sweep on every tick."""

from datetime import datetime, timedelta

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.approval_expiry import expire_overdue
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.scheduler import Scheduler
from my_agent_crew.store.approvals import EXPIRED, PENDING
from my_agent_crew.store.models import IDLE
from my_agent_crew.store.runs import DONE
from my_agent_crew.texts import EXPIRED_TOOL
from tests.conftest import collect

WRITE = ToolCall("c1", "workspace_write", {"path": "out.txt", "content": "muộn"})


async def paused_conversation(deps):
    conv = deps.store.create()
    events = await collect(run_turn(deps, conv.id, "ghi file"))
    return conv, events[-1]


async def test_an_overdue_approval_is_refused_and_the_turn_is_finished_and_delivered(deps_factory):
    deps = deps_factory(script=[completion(tool_calls=(WRITE,)), completion("Thôi, không ghi.")])
    conv, request = await paused_conversation(deps)
    delivered: list[tuple[str, str]] = []

    async def deliver(agent_id: str, conv_id: str) -> bool:
        delivered.append((agent_id, conv_id))
        return True

    hub = ActivityHub(deps.store)
    deadline = datetime.fromisoformat(request.expires_at)
    before = await expire_overdue({deps.agent.id: deps}, hub, deliver, now=deadline - timedelta(1))
    assert before == [] and deps.store.approvals.get(request.approval_id).status == PENDING

    closed = await expire_overdue({deps.agent.id: deps}, hub, deliver, now=deadline)
    assert closed == [request.approval_id]
    approval = deps.store.approvals.get(request.approval_id)
    assert approval.status == EXPIRED and approval.resolved_at
    assert not (deps.settings.workspace_dir / "out.txt").exists()
    history = [m.message for m in deps.store.history(conv.id)]
    assert history[-2].role == "tool" and history[-2].content == EXPIRED_TOOL
    assert history[-1].content == "Thôi, không ghi."
    assert deps.store.get(conv.id).status == IDLE
    assert delivered == [(deps.agent.id, conv.id)]
    run = deps.store.runs.latest_for_conversation(conv.id)
    assert run is not None and run.status == DONE


async def test_a_failing_delivery_still_counts_the_request_as_closed(deps_factory, caplog):
    deps = deps_factory(script=[completion(tool_calls=(WRITE,)), completion("ok")])
    conv, request = await paused_conversation(deps)

    async def deliver(agent_id: str, conv_id: str) -> bool:
        raise RuntimeError("telegram down")

    now = datetime.fromisoformat(request.expires_at)
    closed = await expire_overdue({deps.agent.id: deps}, ActivityHub(deps.store), deliver, now=now)
    assert closed == [request.approval_id]
    assert "resuming after expiry failed" in caplog.text
    assert deps.store.get(conv.id).status == IDLE


async def test_the_scheduler_sweeps_overdue_approvals_on_every_tick(deps_factory):
    deps = deps_factory(
        script=[completion(tool_calls=(WRITE,)), completion("xong")], approval_ttl_seconds=0
    )
    conv, request = await paused_conversation(deps)
    sched = Scheduler({"default": deps}, ActivityHub(deps.store), clock=datetime.now)
    assert await sched.tick() == []  # no job is due; the sweep still ran
    assert deps.store.approvals.get(request.approval_id).status == EXPIRED
    assert deps.store.get(conv.id).status == IDLE


async def test_nothing_to_sweep_is_a_quiet_no_op(deps_factory):
    deps = deps_factory()
    assert await expire_overdue({}, ActivityHub(deps.store)) == []
    assert await expire_overdue({deps.agent.id: deps}, ActivityHub(deps.store)) == []
