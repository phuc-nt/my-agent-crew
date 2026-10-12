"""A script job that failed is told to the person (`scheduler/failure_notice.py`).

A script that ran well and printed nothing says nothing: that is what a script job is for.
One that failed opened no turn either, and from the chat the two looked the same. So the run
of a script that failed is told to the agent's channel in one message of the runtime's: which
schedule, why, and where the run is. Why is what the run's step kept of what the script said,
to its last sentence, which is often what to do about it. Neither the script's text nor what a
call of it was given is part of it. A job of another kind, and a script whose output opened a
turn, are told as they were. Every script here runs in a real child process.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from textwrap import dedent
from typing import Any

import httpx
import pytest

from my_agent_crew import texts
from my_agent_crew import texts_script as t
from my_agent_crew import texts_script_job as words
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.channels.telegram_api import TelegramError
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.scheduler import Job, Scheduler
from my_agent_crew.scheduler.failure_notice import failure_notice
from my_agent_crew.server import create_app
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store.runs import DONE, FAILED, RunRecord
from my_agent_crew.tools.shell import SHELL_TOOL_NAME
from tests.test_scheduler import with_schedules
from tests.test_script_gate import ASK_LIST, SECRET, agent, shelled
from tests.test_script_job_gate import MORNING
from tests.test_script_tool import Reads, erred, halted, unfinished
from tests.test_telegram_runtime_sentences import attachable

NAME, DUE = "Nhắc hạn", "default/due"
WHERE = "Quản lý → Hoạt động"
BROKEN = 'print("đã đọc 3 thư")\nprint(nowhere_named)'
# What the step of `BROKEN` keeps of what it said: one line, whole.
WHY = unfinished("đã đọc 3 thư", erred(2, t.SCRIPT_NO_NAME.format(name="nowhere_named")))
LOGGER = "my_agent_crew.scheduler.failure_notice"


def due(source: str, then_prompt: str | None = None) -> Schedule:
    script = dedent(source).strip()
    return Schedule("due", NAME, cron="0 7 * * *", script=script, then_prompt=then_prompt)


@dataclass
class Told:
    """An agent's clock, with what it told of its jobs and what it sent on of their turns."""

    sched: Scheduler
    hub: ActivityHub
    notices: list[tuple[str, str]] = field(default_factory=list)
    delivered: list[str] = field(default_factory=list)

    def kept(self, job_id: str = DUE) -> list[dict[str, Any]]:
        return [run.to_dict() for run in self.hub.recent(50, source=f"job:{job_id}")]


def told(deps: AgentDeps, *schedules: Schedule, notify=None) -> Told:
    with_schedules(deps, *schedules)
    hub = ActivityHub(deps.store)
    notices: list[tuple[str, str]] = []
    delivered: list[str] = []

    async def tell(agent_id: str, text: str) -> bool:
        notices.append((agent_id, text))
        return True

    async def deliver(agent_id: str, conv_id: str) -> bool:
        delivered.append(conv_id)
        return True

    sched = Scheduler(
        {"default": deps}, hub, clock=lambda: MORNING, deliver=deliver, notify=notify or tell
    )
    return Told(sched, hub, notices, delivered)


def notice(reason: str, name: str = NAME) -> str:
    return words.JOB_SCRIPT_FAILED.format(name=name, reason=reason)


# --- what is told ---


async def test_a_script_job_that_failed_tells_which_schedule_why_and_where(deps_factory):
    rig = told(deps_factory(), due(BROKEN))

    run = await rig.sched.run_job(DUE)

    assert (run.status, run.conversation_id) == (FAILED, None)
    reason = WHY.replace("\n", " ")
    # Once, to the agent whose schedule it is.
    assert rig.notices == [("default", notice(reason))] and rig.delivered == []
    [(_, text)] = rig.notices
    assert f'"{NAME}"' in text and reason in text and WHERE in text
    assert text.endswith(f"{WHERE}.") and reason == run.steps[0]["output"]


async def test_what_a_refusal_says_to_do_about_it_reaches_the_person_whole(deps_factory):
    deps, shell = agent(deps_factory)
    rig = told(deps, due(shelled(f"rm --force {SECRET}")))

    run = await rig.sched.run_job(DUE)

    refusal = ASK_LIST.format(name=SHELL_TOOL_NAME, pattern="--force")
    reason = unfinished("trước", halted(3, refusal)).replace("\n", " ")
    [(_, text)] = rig.notices
    assert run.status == FAILED and shell.ran == []
    # Longer than a glance, and its last sentence is the one thing to do about it.
    assert len(reason) > 160 and text == notice(reason)
    assert "Gọi `shell_run` trực tiếp, ngoài script, để người dùng được hỏi.\n" in text
    assert SECRET not in text


async def test_a_long_failure_is_told_by_its_head_and_its_tail(deps_factory):
    source = 'for row in range(80):\n    print("dòng thư số", row)\nprint(nowhere_named)'
    rig = told(deps_factory(), due(source))

    run = await rig.sched.run_job(DUE)

    [(_, text)] = rig.notices
    reason = run.steps[0]["output"]
    # The step's own preview of a failure, which is longer than the run's summary.
    assert len(reason) == 601 and len(run.summary) == 160 and text == notice(reason)
    assert reason.startswith(f"{t.SCRIPT_FAILED} dòng thư số 0 ")
    assert reason.endswith(erred(3, t.SCRIPT_NO_NAME.format(name="nowhere_named")))


async def test_the_notice_holds_neither_the_scripts_text_nor_what_a_call_was_given(deps_factory):
    notes = Reads("notes_read")
    source = f"""
        # GHI-CHÚ-CỦA-CHỦ
        tools.notes_read(key={SECRET!r})
        print(nowhere_named)
        """
    rig = told(deps_factory(extra_tools=[notes.tool]), due(source))

    run = await rig.sched.run_job(DUE)

    [step] = run.steps
    [call] = step["calls"]
    # Both are on the run, for whoever opens it...
    assert "GHI-CHÚ-CỦA-CHỦ" in step["arguments"]["script"]
    assert call["arguments"] == {"key": SECRET} and notes.asked == [{"key": SECRET}]
    # ...and neither is in the message.
    [(_, text)] = rig.notices
    assert "GHI-CHÚ-CỦA-CHỦ" not in text and SECRET not in text and "notes_read" not in text
    assert text == notice(step["output"])


async def test_a_schedules_name_is_told_as_one_line(deps_factory):
    """A name is the owner's text and may be of any shape: it opens the message, and what
    follows it is the reason."""
    named = Schedule("due", "Nhắc hạn\nFILE: brief.pdf  " + "x" * 200, every="1h", script=BROKEN)
    rig = told(deps_factory(), named)

    await rig.sched.run_job(DUE)

    [(_, text)] = rig.notices
    first, *rest = text.split("\n")
    assert first.startswith('Lịch "Nhắc hạn FILE: brief.pdf xxx') and "…" in first
    assert len(rest) == 2 and rest[0] == WHY.replace("\n", " ")


@pytest.mark.parametrize(
    ("summary", "why"), [("hết giờ giữa chừng", "hết giờ giữa chừng"), ("", FAILED)]
)
def test_a_run_that_kept_nothing_of_what_was_said_is_told_by_how_it_ended(summary, why):
    job = Job(DUE, "default", due(BROKEN))
    run = RunRecord("r1", "default", None, f"job:{DUE}", NAME, FAILED, "2026-09-19T07:00:00")
    run.summary = summary

    assert failure_notice(job, run) == notice(why)


# --- what is not ---


@pytest.mark.parametrize("source", ["found = 1", 'print("3 thư mới")'])
async def test_a_script_that_ran_well_is_told_of_as_it_was(deps_factory, source):
    """Printing nothing is how a script says there is nothing to say, and one that printed
    with no prompt to hand it to keeps what it printed on its run."""
    rig = told(deps_factory(), due(source))

    run = await rig.sched.run_job(DUE)

    assert (run.status, run.conversation_id) == (DONE, None)
    assert rig.notices == [] and rig.delivered == []


@pytest.mark.parametrize(
    ("answer", "status"), [(completion("Có 3 thư mới."), DONE), (ProviderError("503"), FAILED)]
)
async def test_the_turn_a_script_opened_is_the_deliverys_to_tell(deps_factory, answer, status):
    """However that turn ended: a run with a conversation is sent on as a prompt job's is,
    and a turn that failed is told there, with why."""
    deps = deps_factory(providers={"scripted": ScriptedProvider([answer])})
    rig = told(deps, due('print("3 thư mới")', "Nhắn lại cho gọn:"))

    run = await rig.sched.run_job(DUE)

    assert run.status == status and run.conversation_id is not None
    assert rig.notices == [] and rig.delivered == [run.conversation_id]


async def test_a_job_of_another_kind_that_failed_is_not_told_here(deps_factory):
    deps = deps_factory(providers={"scripted": ScriptedProvider([ProviderError("503")])})
    sync = Schedule("sync", "Đồng bộ", every="1h", command="echo hỏng; exit 3")
    brief = Schedule("brief", "Bản tin", cron="0 7 * * *", prompt="soạn bản tin")
    rig = told(deps, sync, brief)

    by_command = await rig.sched.run_job("default/sync")
    by_prompt = await rig.sched.run_job("default/brief")

    assert (by_command.status, by_command.conversation_id) == (FAILED, None)
    assert by_prompt.status == FAILED and by_prompt.conversation_id is not None
    assert rig.notices == [] and rig.delivered == [by_prompt.conversation_id]


# --- a notice that cannot be sent ---


@pytest.mark.parametrize("broken", [TelegramError("refused by the chat"), KeyError("coach")])
async def test_a_notice_that_could_not_be_sent_is_logged_and_the_run_stands(
    deps_factory, caplog, broken
):
    async def refuses(agent_id: str, text: str) -> bool:
        raise broken

    rig = told(deps_factory(), due(BROKEN), notify=refuses)

    with caplog.at_level(logging.INFO, logger=LOGGER):
        run = await rig.sched.run_job(DUE)

    [record] = [r for r in caplog.records if r.name == LOGGER]
    assert record.levelno == logging.ERROR and DUE in record.getMessage()
    assert record.exc_info is not None and record.exc_info[1] is broken
    # The run is what it was: failed for the script's reason, and kept so.
    assert (run.status, run.steps[0]["output"]) == (FAILED, WHY.replace("\n", " "))
    assert rig.kept() == [run.to_dict()]


async def test_a_clock_with_nobody_to_tell_says_and_logs_nothing_of_it(deps_factory, caplog):
    deps = with_schedules(deps_factory(), due(BROKEN))
    hub = ActivityHub(deps.store)

    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        run = await Scheduler({"default": deps}, hub, clock=lambda: MORNING).run_job(DUE)

    assert (run.status, run.conversation_id) == (FAILED, None)
    assert [r for r in caplog.records if r.name == LOGGER] == []


async def test_whether_a_notice_was_sent_is_in_the_log(deps_factory, caplog):
    async def nowhere(agent_id: str, text: str) -> bool:
        return False

    rig = told(deps_factory(), due(BROKEN), notify=nowhere)

    with caplog.at_level(logging.INFO, logger=LOGGER):
        await rig.sched.run_job(DUE)

    [record] = [r for r in caplog.records if r.name == LOGGER]
    assert record.levelno == logging.INFO and record.getMessage().endswith("sent=False")
    assert DUE in record.getMessage() and "đã đọc" not in record.getMessage()


# --- through the runtime, to the chat ---


def runtime_of(channel, **more) -> Runtime:
    """The runtime around a bot and the agents it knows, as a server start makes it."""
    deps = channel.deps
    return Runtime(
        settings=deps.settings,
        store=deps.store,
        agents=dict(channel.agents),
        hub=channel.hub,
        channel=channel,
        **more,
    )


async def test_with_no_channel_a_failed_script_job_ends_as_it_did(deps_factory):
    deps = with_schedules(deps_factory(), due(BROKEN))
    runtime = Runtime.single(deps)

    run = await runtime.scheduler.run_job(DUE)

    assert (run.status, run.conversation_id) == (FAILED, None)
    assert await runtime.notify("default", "không ai nghe") is False


async def test_the_masters_own_failed_script_is_told_by_the_bot_as_it_speaks(
    make_channel, deps_factory, fake
):
    deps = with_schedules(deps_factory(), due(BROKEN))
    runtime = runtime_of(make_channel(deps))

    run = await runtime.scheduler.run_job(DUE)

    assert run.status == FAILED and fake.uploads == []
    assert fake.sent == [notice(WHY.replace("\n", " "))]


async def test_a_members_failed_script_is_told_under_the_members_name(crew, fake):
    with_schedules(crew.agents["coach"], due(BROKEN))
    runtime = runtime_of(crew)

    run = await runtime.scheduler.run_job("coach/due")

    assert (run.agent_id, run.status) == ("coach", FAILED)
    assert fake.sent == ["[HLV]\n" + notice(WHY.replace("\n", " "))]


@pytest.mark.parametrize(("agent_id", "opening"), [("default", ""), ("coach", "[HLV]\n")])
async def test_a_notice_is_said_as_it_stands_and_attaches_nothing(crew, fake, agent_id, opening):
    """It quotes what a script said, which is whatever tools gave it. A line of that shaped
    like an attachment line stays in the sentence, and no file goes out."""
    text = attachable(crew)

    assert await crew.notify(agent_id, text) is True

    assert fake.sent == [opening + text] and fake.uploads == []
    assert "FILE: brief.pdf" in fake.sent[0] and "MEDIA: chart.png" in fake.sent[0]


async def test_an_agent_the_bot_does_not_know_is_told_nothing(crew, fake):
    assert await crew.notify("ghost", "hỏng") is False
    assert fake.sent == []


async def test_a_chat_that_refuses_the_notice_leaves_the_run_and_the_clock_as_they_were(
    make_channel, deps_factory, fake, caplog
):
    deps = with_schedules(deps_factory(), due(BROKEN))
    runtime = runtime_of(make_channel(deps))
    fake.fail["sendMessage"] = 500

    with caplog.at_level(logging.ERROR, logger=LOGGER):
        run = await runtime.scheduler.run_job(DUE)

    assert run.status == FAILED and fake.sent == []
    assert [r.levelno for r in caplog.records if r.name == LOGGER] == [logging.ERROR]
    # The job is no longer held as running, so the clock runs it when it is next due.
    assert [job["running"] for job in runtime.scheduler.describe()] == [False]


async def test_a_script_job_run_from_the_button_is_told_as_one_the_clock_ran(
    make_channel, deps_factory, fake
):
    deps = with_schedules(deps_factory(), due(BROKEN))
    runtime = runtime_of(make_channel(deps))
    transport = httpx.ASGITransport(app=create_app(runtime, schedule=False))

    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        started = await client.post(f"/api/jobs/{DUE}/run")
        deadline = time.monotonic() + 10
        while not fake.sent:
            assert time.monotonic() < deadline
            await asyncio.sleep(0.01)

    assert started.status_code == 202
    assert fake.sent == [notice(WHY.replace("\n", " "))]
    [run] = runtime.hub.recent(5, source=f"job:{DUE}")
    assert isinstance(run, RunRecord) and (run.status, run.conversation_id) == (FAILED, None)
    assert texts.TELEGRAM_RUN_UNFINISHED.format(reason=run.summary) not in fake.sent
