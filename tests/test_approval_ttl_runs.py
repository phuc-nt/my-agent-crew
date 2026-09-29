"""Where a running conversation's approvals get their wait: from the schedule that opened
it, the Telegram chat it came in on, or the parent that delegated it, and never from
whichever deps happen to be answering, which after a restart are not the ones that asked.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

import my_agent_crew.tools.delegate as delegate_tool
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.resume import answer_question
from my_agent_crew.agents.approval_ttl import MIN_TTL
from my_agent_crew.agents.channels import TelegramConfig
from my_agent_crew.agents.schedule import Schedule
from my_agent_crew.config import Route
from my_agent_crew.inbound import Inbound
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.scheduler import Scheduler
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store import Store
from my_agent_crew.store.models import Approval
from tests.conftest import collect, make_deps
from tests.test_scheduler import with_schedules
from tests.test_tools_delegate import agent, delegation_result, wait_until_paused

ASKING = ToolCall("q1", "ask_user", {"question": "Ghi báo cáo?", "options": ["có", "không"]})
ASKING_AGAIN = ToolCall("q2", "ask_user", {"question": "Gửi luôn?", "options": ["có", "không"]})
NIGHTLY = Schedule(
    "nightly", "Báo cáo đêm", cron="0 3 * * *", prompt="làm báo cáo", approval_ttl_seconds=7200
)
NIGHT = datetime(2026, 9, 29, 3, 0)
WRITE_TASK = '/tool workspace_write {"path": "x.txt", "content": "1"}'


def waits(approval: Approval) -> timedelta:
    return datetime.fromisoformat(approval.expires_at) - datetime.fromisoformat(approval.created_at)


async def asking_job(settings, store: Store):
    deps = make_deps(settings, store, script=[completion(tool_calls=(ASKING,))])
    deps = with_schedules(deps, NIGHTLY)
    scheduler = Scheduler({"default": deps}, ActivityHub(store), clock=lambda: NIGHT)
    return await scheduler.run_job("default/nightly")


async def test_a_job_that_asks_waits_as_long_as_its_schedule_says(settings, store: Store):
    run = await asking_job(settings, store)

    conv = store.get(run.conversation_id)
    assert conv.approval_ttl_seconds == 7200
    assert waits(store.approvals.pending(conv.id)) == timedelta(seconds=7200)
    assert settings.approval_ttl_seconds != 7200


async def test_the_next_question_after_a_restart_waits_as_long_again(settings, store: Store):
    run = await asking_job(settings, store)
    first = store.approvals.pending(run.conversation_id)
    # A restarted server answers with deps that were never told about the schedule.
    fresh = make_deps(settings, store, script=[completion(tool_calls=(ASKING_AGAIN,))])

    await collect(answer_question(fresh, run.conversation_id, first.id, "có"))

    second = store.approvals.pending(run.conversation_id)
    assert second.id != first.id and waits(second) == timedelta(seconds=7200)


def test_a_telegram_conversation_waits_as_long_as_its_channel_says(deps_factory):
    deps = deps_factory()
    telegram = TelegramConfig("CHAT_TTL_TEST_TOKEN", 42, approval_ttl_seconds=900)
    deps = replace(deps, profile=replace(deps.profile, telegram=telegram))
    inbound = Inbound({deps.agent.id: deps}, ActivityHub(deps.store))

    assert inbound.open_conversation(deps.agent.id, "telegram:42").approval_ttl_seconds == 900
    assert inbound.open_conversation(deps.agent.id, "web").approval_ttl_seconds is None


@pytest.fixture
def runtime(deps_factory, store: Store) -> Runtime:
    """A boss that delegates to a worker whose own wait differs from the crew's."""
    base = deps_factory(routes=(Route("fake", "echo"),))
    worker = agent(base, "worker")
    agents = {
        "boss": agent(base, "boss", delegates=("worker",)),
        "worker": replace(worker, settings=replace(worker.settings, approval_ttl_seconds=1234)),
    }
    rt = Runtime(base.settings, store, agents, ActivityHub(store))
    rt.wire_delegation()
    return rt


def recorded_waits(runtime: Runtime, monkeypatch) -> list[float]:
    asked: list[float] = []
    real_wait = runtime.hub.wait_finished

    async def recording(conv_id: str, timeout: float):
        asked.append(timeout)
        return await real_wait(conv_id, 5.0)

    monkeypatch.setattr(runtime.hub, "wait_finished", recording)
    return asked


async def test_a_child_waits_as_long_as_its_parent_and_the_parent_waits_for_that(
    runtime: Runtime, monkeypatch
):
    asked = recorded_waits(runtime, monkeypatch)
    parent = runtime.store.create(agent_id="boss", autonomous=True, approval_ttl_seconds=7200)

    await delegation_result(runtime, parent.id, "call-1", task="việc", agent="worker")

    assert runtime.store.for_parent_call("call-1").approval_ttl_seconds == 7200
    assert asked == [7200 + delegate_tool.WAIT_MARGIN_SECONDS]


async def test_without_one_the_parent_waits_as_long_as_the_child_agent_would(
    runtime: Runtime, monkeypatch
):
    asked = recorded_waits(runtime, monkeypatch)
    parent = runtime.store.create(agent_id="boss", autonomous=True)

    await delegation_result(runtime, parent.id, "call-1", task="việc", agent="worker")

    assert runtime.store.for_parent_call("call-1").approval_ttl_seconds is None
    assert runtime.settings.approval_ttl_seconds != 1234
    assert asked == [1234 + delegate_tool.WAIT_MARGIN_SECONDS]


async def test_a_child_found_again_keeps_the_wait_it_was_opened_with(runtime: Runtime, monkeypatch):
    asked = recorded_waits(runtime, monkeypatch)
    parent = runtime.store.create(agent_id="boss", autonomous=True, approval_ttl_seconds=7200)
    await delegation_result(runtime, parent.id, "call-1", task="việc", agent="worker")
    runtime.store._conn.execute(
        "UPDATE conversations SET approval_ttl_seconds = 300 WHERE id = ?", (parent.id,)
    )

    await delegation_result(runtime, parent.id, "call-1", task="việc", agent="worker")

    assert asked == [7200 + delegate_tool.WAIT_MARGIN_SECONDS] * 2


async def test_the_parent_stops_waiting_once_the_childs_own_wait_is_over(
    runtime: Runtime, monkeypatch
):
    """With the margin taken away the wait is the child's minute less a moment, so the
    child is still parked on its approval when the parent gives up on it."""
    monkeypatch.setattr(delegate_tool, "WAIT_MARGIN_SECONDS", -(MIN_TTL - 0.05))
    parent = runtime.store.create(agent_id="boss", autonomous=False, approval_ttl_seconds=MIN_TTL)

    result = await asyncio.wait_for(
        delegation_result(runtime, parent.id, "call-1", task=WRITE_TASK, agent="worker"), 5
    )

    assert not result.ok
    assert result.output.splitlines()[1] == "outcome=failed reason=timeout"
    await wait_until_paused(runtime)
