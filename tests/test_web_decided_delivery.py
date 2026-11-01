"""Which answers reach the chat when a request is settled away from it.

A request decided on the web, or one nobody answered, finishes its turn there. The chat hears
the answer only when it is the one waiting for it: a job's, or one of the chat's own
conversations. A conversation of the web's is read on the web, so its answer, and the line
saying its request ran out, stay out of the chat.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from my_agent_crew.agent.approval_expiry import expire_overdue
from my_agent_crew.agent.events import ApprovalRequiredEvent
from my_agent_crew.agent.loop import run_turn
from my_agent_crew.agent.turn_context import TELEGRAM
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.llm.fake import completion
from my_agent_crew.server import create_app
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store.models import QUESTION
from my_agent_crew.store.runs import AWAITING
from tests.conftest import collect
from tests.lapse_helpers import ASK, WRITE
from tests.test_scheduler import with_schedules

CHECK = Schedule("deadline-check", "Nhắc hạn", cron="30 7 * * *", prompt="Có hạn nào không?")


def runtime_of(channel) -> Runtime:
    deps = channel.deps
    return Runtime(
        settings=deps.settings,
        store=deps.store,
        agents=dict(channel.agents),
        hub=channel.hub,
        channel=channel,
    )


def scripted(deps_factory, answer: str, call=WRITE):
    """A run whose model stops on `call`, then answers. A job runs a workspace write on its
    own, so a job's run stops on a question instead."""
    script = [completion(tool_calls=(call,)), completion(answer)]
    return with_schedules(deps_factory(script=script), CHECK)


async def paused_on_web(deps) -> str:
    conv = deps.store.create(agent_id=deps.agent.id)
    events = await collect(run_turn(deps, conv.id, "ghi file"))
    assert isinstance(events[-1], ApprovalRequiredEvent)
    return conv.id


async def paused_job(runtime: Runtime) -> str:
    run = await runtime.scheduler.run_job(f"{runtime.default.agent.id}/{CHECK.id}")
    assert run.status == AWAITING and run.conversation_id
    return run.conversation_id


def approve(runtime: Runtime, conv_id: str) -> None:
    """Settles the conversation's request on the web: allows a tool call, answers a question."""
    approval = runtime.store.approvals.pending(conv_id)
    assert approval is not None
    url = f"/api/conversations/{conv_id}/approvals/{approval.id}"
    body: dict = {"approve": True}
    if approval.kind == QUESTION:
        url, body = f"{url}/answer", {"answer": "chạy"}
    with TestClient(create_app(runtime, schedule=False), base_url="http://127.0.0.1") as client:
        with client.stream("POST", url, json=body) as r:
            assert r.status_code == 200
            "".join(r.iter_text())


async def test_a_web_conversation_that_ran_out_tells_the_chat_nothing(
    make_channel, deps_factory, fake
):
    runtime = runtime_of(make_channel(scripted(deps_factory, "Thôi, không ghi.")))
    conv_id = await paused_on_web(runtime.default)
    later = datetime.now(UTC) + timedelta(seconds=runtime.settings.approval_ttl_seconds + 1)

    closed = await expire_overdue(runtime.agents, runtime.hub, runtime.deliver, now=later)

    assert len(closed) == 1
    assert runtime.store.history(conv_id)[-1].message.content == "Thôi, không ghi."
    assert fake.sent == []


async def test_a_job_that_ran_out_still_reports_to_the_chat(make_channel, deps_factory, fake):
    runtime = runtime_of(make_channel(scripted(deps_factory, "Chạy nhé.", ASK)))
    await paused_job(runtime)
    fake.sent.clear()
    later = datetime.now(UTC) + timedelta(seconds=runtime.settings.approval_ttl_seconds + 1)

    await expire_overdue(runtime.agents, runtime.hub, runtime.deliver, now=later)

    assert fake.sent == ["Chạy nhé."]


async def test_a_job_approved_on_the_web_reports_its_answer_to_the_chat(
    make_channel, deps_factory, fake
):
    runtime = runtime_of(make_channel(scripted(deps_factory, "Chạy nhé.", ASK)))
    conv_id = await paused_job(runtime)
    fake.sent.clear()

    approve(runtime, conv_id)

    assert fake.sent == ["Chạy nhé."]


async def test_the_chats_own_conversation_approved_on_the_web_answers_in_the_chat(
    make_channel, deps_factory, fake
):
    channel = make_channel(scripted(deps_factory, "Đã ghi xong."))
    runtime = runtime_of(channel)
    conv = channel.open_conversation()
    events = await collect(run_turn(runtime.default, conv.id, "ghi file", source=TELEGRAM))
    assert isinstance(events[-1], ApprovalRequiredEvent)

    approve(runtime, conv.id)

    assert fake.sent == ["Đã ghi xong."]


async def test_a_web_conversation_approved_on_the_web_stays_out_of_the_chat(
    make_channel, deps_factory, fake
):
    runtime = runtime_of(make_channel(scripted(deps_factory, "Đã ghi xong.")))
    conv_id = await paused_on_web(runtime.default)

    approve(runtime, conv_id)

    assert runtime.store.history(conv_id)[-1].message.content == "Đã ghi xong."
    assert fake.sent == []
