"""Who reads a turn that is carried on after a restart (`turn_resume.py`).

Nobody is waiting on the HTTP request that began it any more. A chat's turn is answered by
the bot, a job's by the scheduler's delivery, and a delegated task by the turn that handed
it out, which is carried on first and finds its child again."""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from my_agent_crew import texts
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.channels import telegram_polling
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import ToolCall
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store.runs import DONE, FAILED, RUNNING, RunRecord
from my_agent_crew.tools.delegate import DELEGATE_TOOL_NAME
from my_agent_crew.turn_resume import resume_cut_turns
from tests.queue_helpers import GatedProvider, SlowTool, settle_loop, until
from tests.restart_helpers import (
    carried_on,
    cut_mid_tool,
    go_down,
    history,
    next_server,
    stored_run,
)
from tests.telegram_fake import message, settle
from tests.test_scheduler import with_schedules

SLOW = ToolCall("c1", "slow", {})
PEEK = ToolCall("p1", "peek", {})
BRIEF = Schedule("brief", "Bản tin sáng", cron="0 7 * * *", prompt="soạn bản tin")
JOB_ID = "default/brief"


def crew_with_bot(make_channel, deps_factory, script, *schedules: Schedule):
    """One agent, its bot and the runtime around both, as a server start builds them."""
    slow = SlowTool()
    deps = deps_factory(providers={"scripted": GatedProvider(script)}, extra_tools=[slow.tool])
    deps = with_schedules(deps, *schedules)
    channel = make_channel(deps)
    runtime = Runtime(
        settings=deps.settings,
        store=deps.store,
        agents={deps.agent.id: deps},
        hub=channel.hub,
        channel=channel,
    )
    runtime.channel_live = True
    return runtime, channel, slow


async def chat_turn_under_way(channel, fake, slow) -> str:
    fake.updates = [message(1, "việc dài")]
    await channel.poll_once()
    await asyncio.wait_for(slow.started.wait(), 2)
    return channel.conversation().id


async def bot_stops(channel, fake) -> None:
    fake.status = 409  # the loop backs off instead of spinning on an empty fake
    channel.start()
    await channel.stop()
    fake.status = None


def chat_history(runtime: Runtime, conv_id: str) -> list[tuple[str, str]]:
    return [(m.message.role, m.message.content) for m in runtime.store.history(conv_id)]


async def test_a_chat_turn_cut_by_the_server_is_answered_by_the_bot_that_starts_next(
    make_channel, deps_factory, fake, monkeypatch
):
    monkeypatch.setattr(telegram_polling, "STOP_GRACE_SECONDS", 0.05)
    first, channel, slow = crew_with_bot(
        make_channel, deps_factory, [completion(tool_calls=[SLOW])]
    )
    conv_id = await chat_turn_under_way(channel, fake, slow)
    first.hub.going_down = True
    await bot_stops(channel, fake)
    # The person is told the truth: it was cut, and it will be carried on.
    assert fake.sent == [texts.TELEGRAM_CUT_RESUMES]
    cut = first.store.runs.latest_for_conversation(conv_id)
    assert cut is not None and (cut.status, cut.source) == (RUNNING, "telegram")

    second, bot, again = crew_with_bot(make_channel, deps_factory, [completion("đã kiểm tra")])
    assert [run.id for run in resume_cut_turns(second)] == [cut.id]
    await settle(bot)

    assert fake.sent[1:] == ["đã kiểm tra"] and again.runs == 0
    run = second.store.runs.latest_for_conversation(conv_id)
    assert run is not None and (run.id, run.status, run.resumed) == (cut.id, DONE, True)
    assert chat_history(second, conv_id)[-2:] == [
        ("tool", texts.RESTART_CUT_TOOL),
        ("assistant", "đã kiểm tra"),
    ]


async def test_a_bot_restarted_while_the_server_stays_up_promises_nothing(
    make_channel, deps_factory, fake, monkeypatch
):
    """Nothing starts next to carry the turn on, so the notice must not say it will be."""
    monkeypatch.setattr(telegram_polling, "STOP_GRACE_SECONDS", 0.05)
    runtime, channel, slow = crew_with_bot(
        make_channel, deps_factory, [completion(tool_calls=[SLOW])]
    )
    conv_id = await chat_turn_under_way(channel, fake, slow)

    await bot_stops(channel, fake)

    assert fake.sent == [texts.TELEGRAM_CUT_OFF]
    run = runtime.store.runs.latest_for_conversation(conv_id)
    assert run is not None and (run.status, run.summary) == (FAILED, "interrupted")


async def test_a_chat_turn_is_left_closed_when_no_bot_is_up_to_answer_it(
    make_channel, deps_factory, fake, monkeypatch
):
    """Carried on unread, its answer would sit in the log with nobody told."""
    monkeypatch.setattr(telegram_polling, "STOP_GRACE_SECONDS", 0.05)
    first, channel, slow = crew_with_bot(
        make_channel, deps_factory, [completion(tool_calls=[SLOW])]
    )
    conv_id = await chat_turn_under_way(channel, fake, slow)
    first.hub.going_down = True
    await bot_stops(channel, fake)

    second, _, _ = crew_with_bot(make_channel, deps_factory, [completion("không được hỏi")])
    second.channel_live = False  # the bot's token was taken away, or it failed to start

    assert resume_cut_turns(second) == []
    run = second.store.runs.latest_for_conversation(conv_id)
    assert run is not None and (run.status, run.summary) == (FAILED, "interrupted")
    assert fake.sent == [texts.TELEGRAM_CUT_RESUMES]
    assert not second.hub.busy.busy(conv_id)


async def job_cut_mid_tool(make_channel, deps_factory) -> tuple[Runtime, RunRecord]:
    first, _, slow = crew_with_bot(
        make_channel, deps_factory, [completion(tool_calls=[SLOW])], BRIEF
    )
    first.scheduler.keep(asyncio.create_task(first.scheduler.run_job(JOB_ID)))
    await asyncio.wait_for(slow.started.wait(), 2)
    await go_down(first)
    [cut] = first.store.runs.recent(source=f"job:{JOB_ID}")
    assert cut.status == RUNNING
    return first, cut


async def ended(runtime: Runtime, conv_id: str) -> RunRecord:
    await until(lambda: not runtime.hub.busy.busy(conv_id))
    await settle_loop()  # the push to the chat comes after the turn, in the same task
    run = runtime.store.runs.latest_for_conversation(conv_id)
    assert run is not None
    return run


async def test_a_job_cut_by_a_restart_is_carried_on_and_its_answer_reaches_the_chat(
    make_channel, deps_factory, fake
):
    _, cut = await job_cut_mid_tool(make_channel, deps_factory)
    assert fake.sent == []

    second, _, again = crew_with_bot(
        make_channel, deps_factory, [completion("Bản tin: trời đẹp.")], BRIEF
    )
    assert [run.id for run in resume_cut_turns(second)] == [cut.id]
    run = await ended(second, cut.conversation_id)
    await until(lambda: fake.sent)

    assert (run.id, run.status, run.source) == (cut.id, DONE, f"job:{JOB_ID}")
    assert again.runs == 0
    # Pushed once, as the scheduler pushes the answer of a job that ran in one piece.
    [pushed] = fake.sent
    assert "Bản tin: trời đẹp." in pushed
    # And it is the job's last run on the Jobs page, not a stray turn.
    assert second.scheduler.describe()[0]["last_run"]["id"] == cut.id


async def test_a_job_removed_meanwhile_is_carried_on_and_tells_nobody(
    make_channel, deps_factory, fake
):
    _, cut = await job_cut_mid_tool(make_channel, deps_factory)

    second, _, _ = crew_with_bot(make_channel, deps_factory, [completion("Bản tin: trời đẹp.")])
    resume_cut_turns(second)
    run = await ended(second, cut.conversation_id)

    assert (run.id, run.status) == (cut.id, DONE) and fake.sent == []


def delegating(task: str = "việc con", **args) -> ToolCall:
    return ToolCall("d1", DELEGATE_TOOL_NAME, {"task": task, **args})


def child_of(app, call_id: str = "d1"):
    child = app.runtime.store.for_parent_call(call_id, f"delegate:{app.conv.id}")
    assert child is not None
    return child


async def test_a_delegating_turn_and_its_child_are_both_carried_on_and_meet_again(served):
    """The parent's call is made again and finds the child it opened, so the task is not
    handed out a second time; the child goes on from where it was cut."""
    # The parent and its child are the same agent here, so they read one script in turn.
    first = served(
        [completion(tool_calls=[delegating(relay=False)]), completion(tool_calls=[SLOW])]
    )
    parent_cut = await cut_mid_tool(first)
    child = child_of(first)
    child_cut = first.runtime.store.runs.latest_for_conversation(child.id)
    assert child_cut is not None
    assert (parent_cut.status, child_cut.status) == (RUNNING, RUNNING)
    assert child_cut.source == f"delegate:{first.conv.id}"

    second = next_server(served, first, [completion("con xong"), completion("cha xong")])
    taken = resume_cut_turns(second.runtime)
    assert [run.id for run in taken] == [parent_cut.id, child_cut.id]
    parent_run = await carried_on(second)

    store = second.runtime.store
    child_run = store.runs.latest_for_conversation(child.id)
    assert child_run is not None
    assert (parent_run.id, parent_run.status) == (parent_cut.id, DONE)
    assert (child_run.id, child_run.status, child_run.resumed) == (child_cut.id, DONE, True)
    assert [c.id for c in store.delegated_children(second.conv.id, DELEGATE_TOOL_NAME)] == [
        child.id
    ]
    assert second.slow.runs == 0
    assert history(second, child.id)[-2:] == [
        ("tool", texts.RESTART_CUT_TOOL),
        ("assistant", "con xong"),
    ]
    role, result = history(second)[-2]
    assert role == "tool" and "con xong" in result and f"conversation={child.id}" in result
    assert history(second)[-1] == ("assistant", "cha xong")
    # The child goes on as a child: a task handed down is not handed down again.
    child_asked, parent_asked = second.provider.requests
    assert DELEGATE_TOOL_NAME in {tool.name for tool in parent_asked.tools}
    assert DELEGATE_TOOL_NAME not in {tool.name for tool in child_asked.tools}
    # Two model calls each, and the child's spend counted on the parent once.
    assert store.get(child.id).spent_usd == pytest.approx(0.002)
    assert store.get(second.conv.id).spent_usd == pytest.approx(0.004)


def reading_alongside() -> SlowTool:
    """A read that runs in the same batch as a delegation: results of a batch are written
    only when every call in it has ended, so cutting this one leaves both without one."""
    peek = SlowTool("peek", replay_safe=True)
    peek.tool = replace(peek.tool, parallel=True)
    return peek


async def test_a_child_that_had_ended_is_read_from_the_store_by_the_parent_carried_on(served):
    """The parent was cut on another call of the same batch, after its child was done:
    no signal of that child's end exists in the process that starts next."""
    peek = reading_alongside()
    calls = [delegating(relay=False), PEEK]
    first = served([completion(tool_calls=calls), completion("con xong")], extra_tools=[peek.tool])
    parent_cut = await cut_mid_tool(first, peek)
    child = child_of(first)
    await until(lambda: stored_run(first, child.id).status == DONE)
    assert [role for role, _ in history(first)] == ["user", "assistant"]  # no result stored

    again = reading_alongside()
    again.release.set()
    second = next_server(served, first, [completion("cha xong")], extra_tools=[again.tool])
    assert [run.id for run in resume_cut_turns(second.runtime)] == [parent_cut.id]
    run = await carried_on(second)

    assert (run.id, run.status) == (parent_cut.id, DONE)
    results = [said for role, said in history(second) if role == "tool"]
    assert len(results) == 2 and "con xong" in results[0] and results[1] == "xong"
    assert history(second)[-1] == ("assistant", "cha xong")
    assert len(second.provider.requests) == 1  # the child was not asked again
    assert [c.id for c in second.runtime.store.delegated_children(second.conv.id, "delegate")] == [
        child.id
    ]


async def test_a_child_done_before_the_cut_costs_its_parent_what_it_spent_once(served):
    """The delegation itself had ended and only the read beside it was still running. Made
    again by the parent carried on, it finds the same child and the same spend: a call
    costs its conversation what its result does, when that is written and not before."""
    peek = reading_alongside()
    calls = [delegating(relay=False), PEEK]
    first = served([completion(tool_calls=calls), completion("con xong")], extra_tools=[peek.tool])
    store = first.runtime.store
    sender = asyncio.create_task(first.client.post(first.messages, json={"text": "làm đi"}))
    await asyncio.wait_for(peek.started.wait(), 2)
    child = child_of(first)
    await until(lambda: stored_run(first, child.id).status == DONE)
    await settle_loop()  # the delegation returns once its child's run is closed
    assert [role for role, _ in history(first)] == ["user", "assistant"]  # no result stored
    assert store.get(child.id).spent_usd == pytest.approx(0.001)
    assert store.get(first.conv.id).spent_usd == pytest.approx(0.001)  # its own call so far
    await go_down(first.runtime)
    await asyncio.wait_for(sender, 2)

    again = reading_alongside()
    again.release.set()
    second = next_server(served, first, [completion("cha xong")], extra_tools=[again.tool])
    await carried_on(second)

    assert history(second)[-1] == ("assistant", "cha xong")
    # Three model calls in all: the parent's two and the child's one.
    assert first.provider.calls + second.provider.calls == 3
    assert store.get(first.conv.id).spent_usd == pytest.approx(0.003)


async def test_a_delegated_task_is_not_carried_on_without_the_turn_that_waits_for_it(served):
    """Its answer goes to the parent's call and nowhere else: with no parent turn to take
    it, the work would be paid for and read by nobody."""
    first = served([completion(tool_calls=[delegating()]), completion(tool_calls=[SLOW])])
    parent_cut = await cut_mid_tool(first)
    child = child_of(first)
    # The parent's conversation spent its budget, so its turn is not taken up.
    first.runtime.store.add_spend(first.conv.id, first.conv.cost_cap_usd)

    second = next_server(served, first, [completion("không được hỏi")])

    assert resume_cut_turns(second.runtime) == []
    for conv_id, run_id in ((second.conv.id, parent_cut.id), (child.id, None)):
        closed = second.runtime.store.runs.latest_for_conversation(conv_id)
        assert closed is not None and (closed.status, closed.summary) == (FAILED, "interrupted")
        assert run_id is None or closed.id == run_id
    assert second.provider.requests == []
