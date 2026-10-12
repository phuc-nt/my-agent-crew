"""A script job that failed is told to the person (`scheduler/failure_notice.py`).

A script that ran well and printed nothing says nothing: that is what a script job is for.
One that failed opened no turn either, and from the chat the two looked the same. So the run
of a script that failed is told to the agent's channel in one message of the runtime's: which
schedule, why, and where the run is. Why is what ended the script: the line of its error, or
the line that says nothing of it could be kept, to its last sentence, which is often what to
do about it. Nothing the script printed before it failed is part of it, and neither is the
script's text. What a call was given is in it only where the tool that failed said it back,
and what an error the script raised says is in it as the script wrote it. The run's step keeps
all the script said, and is not made from the message, nor the message from it; its summary
is what ended the script too, cut shorter (`test_job_run_summary.py`). A job of another kind,
and a script whose output opened a turn, are told as they were.
Every script here runs in a real child process.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import timedelta
from textwrap import dedent
from typing import Any

import httpx
import pytest

from my_agent_crew import texts
from my_agent_crew import texts_script as t
from my_agent_crew import texts_script_job as words
from my_agent_crew.activity import ActivityHub
from my_agent_crew.activity.step_previews import (
    CUT,
    FAILURE_HEAD,
    FAILURE_TAIL,
    PREVIEW_CHARS,
)
from my_agent_crew.agent.loop import AgentDeps
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.channels.telegram_api import TelegramError
from my_agent_crew.llm.fake import ScriptedProvider, completion
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.scheduler import Job, Scheduler, script_job
from my_agent_crew.scheduler.failure_notice import failure_notice
from my_agent_crew.script import limits
from my_agent_crew.script.store_session import job_kept
from my_agent_crew.server import create_app
from my_agent_crew.server.runtime import Runtime
from my_agent_crew.store.runs import DONE, FAILED, RunRecord
from my_agent_crew.texts_script_store import STORE_NOT_KEPT
from my_agent_crew.tools.registry import Tool, ToolError
from my_agent_crew.tools.shell import SHELL_TOOL_NAME
from tests.test_scheduler import with_schedules
from tests.test_script_gate import ASK_LIST, SECRET, agent, shelled
from tests.test_script_job_gate import MORNING
from tests.test_script_tool import SCHEMA, Reads, erred, halted, unfinished
from tests.test_telegram_runtime_sentences import attachable

NAME, DUE = "Nhắc hạn", "default/due"
WHERE = "Quản lý → Hoạt động"
BROKEN = 'print("đã đọc 3 thư")\nprint(nowhere_named)'
# What ended `BROKEN`, which is why it failed and all the person is told of it...
WHY = erred(2, t.SCRIPT_NO_NAME.format(name="nowhere_named"))
# ...and what its run's step keeps of what it said: one line, whole, with what it printed.
STEP = unfinished("đã đọc 3 thư", WHY).replace("\n", " ")
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
    # Once, to the agent whose schedule it is.
    assert rig.notices == [("default", notice(WHY))] and rig.delivered == []
    [(_, text)] = rig.notices
    assert f'"{NAME}"' in text and WHY in text and WHERE in text
    assert text.endswith(f"{WHERE}.") and text.split("\n")[1] == WHY


async def test_what_a_script_printed_before_it_failed_is_not_told(deps_factory):
    """What a script prints is whatever its tools gave it: a mail, a page, a note somebody
    else wrote. It is on the run, for whoever opens that, and no part of the message."""
    mail = Reads("mail_read", "Kính gửi anh Phúc, mã xác nhận của anh là 4471.")
    source = """
        print("đã đọc 3 thư")
        print(tools.mail_read())
        print(nowhere_named)
        """
    rig = told(deps_factory(extra_tools=[mail.tool]), due(source))

    run = await rig.sched.run_job(DUE)

    ended = erred(3, t.SCRIPT_NO_NAME.format(name="nowhere_named"))
    [(_, text)] = rig.notices
    assert text == notice(ended)
    assert "đã đọc" not in text and "4471" not in text and "Kính gửi" not in text
    # The run's step holds what was said, printed lines and all. Its summary is what ended
    # the script, as the message is, and holds none of those lines either.
    said = unfinished("đã đọc 3 thư", mail.answer, ended)
    [step] = run.steps
    assert (step["ok"], step["output"]) == (False, said.replace("\n", " "))
    assert (run.status, run.summary) == (FAILED, ended)
    assert rig.kept() == [run.to_dict()]


async def test_a_tool_that_failed_is_told_in_its_own_words_and_so_is_what_it_said_back(
    deps_factory,
):
    """Why a tool failed is the tool's to say, and is why the script ended. A tool that
    names what it was asked for says it here too: the message holds it for that reason and
    no other."""

    async def no_such_note(arguments: dict[str, Any]) -> str:
        raise ToolError(f"không có ghi chú tên {arguments['key']}")

    named = {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}
    notes = Tool("notes_read", "Đọc ghi chú.", named, no_such_note, replay_safe=True)
    source = """
        print("bắt đầu")
        tools.notes_read(key="hop-dong-so-7")
        """
    rig = told(deps_factory(extra_tools=[notes]), due(source))

    run = await rig.sched.run_job(DUE)

    own = texts.TOOL_FAILED.format(error="không có ghi chú tên hop-dong-so-7")
    [(_, text)] = rig.notices
    assert run.status == FAILED and text == notice(erred(2, own))
    assert "hop-dong-so-7" in text and "bắt đầu" not in text


async def test_what_an_error_the_script_raised_says_is_told(deps_factory):
    source = """
        print("3 dòng sổ")
        raise ValueError("thiếu cột ngày ở dòng 2 của sổ")
        """
    rig = told(deps_factory(), due(source))

    run = await rig.sched.run_job(DUE)

    [(_, text)] = rig.notices
    assert run.status == FAILED
    assert text == notice(erred(2, "ValueError: thiếu cột ngày ở dòng 2 của sổ"))
    assert "3 dòng sổ" not in text


async def test_a_script_that_ended_well_and_kept_nothing_is_told_by_the_line_that_says_so(
    deps_factory, monkeypatch
):
    """Another run filled the schedule's store while this one ran, and what this one stored
    no longer fits beside it: it ran to its end, and the run failed. What ended it is that
    one line, and what it printed on the way is not told."""
    most = 60
    monkeypatch.setattr(limits, "MAX_STORE_TOTAL_CHARS", most)
    theirs = {"theirs": '"' + "y" * 40 + '"'}

    async def other_run_ends(arguments: dict[str, Any]) -> str:
        store, namespace = deps.store.script_store, job_kept(deps, "due").namespace
        assert store.apply(deps.agent.id, namespace, theirs, most)
        return "xong"

    other = Tool("other_run_ends", "Đọc.", SCHEMA, other_run_ends, replay_safe=True)
    deps = deps_factory(extra_tools=[other])
    source = """
        store("mine", "x" * 30)
        tools.other_run_ends()
        print("đã xem 3 thư")
        """
    rig = told(deps, due(source))

    run = await rig.sched.run_job(DUE)

    lost = STORE_NOT_KEPT.format(most=most)
    [(_, text)] = rig.notices
    assert (run.status, run.conversation_id) == (FAILED, None)
    assert text == notice(lost) and "đã xem" not in text
    assert run.steps[0]["output"] == unfinished("đã xem 3 thư", lost).replace("\n", " ")


async def test_a_job_whose_script_could_not_be_run_at_all_is_told_by_the_kind_of_error(
    deps_factory, monkeypatch
):
    async def breaks(*args: Any, **kwargs: Any):
        raise RuntimeError("đường dẫn riêng của máy")

    monkeypatch.setattr(script_job, "run_source", breaks)
    rig = told(deps_factory(), due(BROKEN))

    run = await rig.sched.run_job(DUE)

    # As the run names it: the kind of error, and no more of it.
    said = texts.TOOL_FAILED.format(error="RuntimeError")
    assert (run.status, run.steps[0]["output"]) == (FAILED, said)
    assert rig.notices == [("default", notice(said))]


async def test_what_a_refusal_says_to_do_about_it_reaches_the_person_whole(deps_factory):
    deps, shell = agent(deps_factory)
    rig = told(deps, due(shelled(f"rm --force {SECRET}")))

    run = await rig.sched.run_job(DUE)

    refusal = ASK_LIST.format(name=SHELL_TOOL_NAME, pattern="--force")
    reason = halted(3, refusal)
    [(_, text)] = rig.notices
    assert run.status == FAILED and shell.ran == []
    # Longer than a glance, and its last sentence is the one thing to do about it.
    assert len(reason) > 160 and text == notice(reason)
    assert "Gọi `shell_run` trực tiếp, ngoài script, để người dùng được hỏi.\n" in text
    assert SECRET not in text and "trước" not in text
    # The step keeps what the script had printed by then, ahead of the same refusal.
    assert run.steps[0]["output"] == unfinished("trước", reason).replace("\n", " ")


async def test_a_long_failure_is_told_by_its_head_and_its_tail(deps_factory):
    """The same cut a failed step is kept by, made of what ended the script alone."""
    source = 'print("in trước")\nraise ValueError("mở đầu " + "x" * 700 + " việc cần làm")'
    rig = told(deps_factory(), due(source))

    run = await rig.sched.run_job(DUE)

    [(_, text)] = rig.notices
    whole = erred(2, "ValueError: mở đầu " + "x" * 700 + " việc cần làm")
    reason = whole[:FAILURE_HEAD] + CUT + whole[-FAILURE_TAIL:]
    # Longer than the run's summary, which is the start alone, and to the last thing the
    # error said.
    assert len(reason) == 601 and text == notice(reason)
    assert run.summary == whole[:PREVIEW_CHARS] + CUT
    assert reason.startswith(erred(2, "ValueError: mở đầu xxx"))
    assert reason.endswith("xxx việc cần làm")
    # The step is cut the same way, of a text that begins with what was printed.
    kept = run.steps[0]["output"]
    assert len(kept) == 601 and kept.startswith(f"{t.SCRIPT_FAILED} in trước {whole[:20]}")


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
    assert text == notice(erred(3, t.SCRIPT_NO_NAME.format(name="nowhere_named")))


async def test_a_schedules_name_is_told_as_one_line(deps_factory):
    """A name is the owner's text and may be of any shape: it opens the message, and what
    follows it is the reason."""
    named = Schedule("due", "Nhắc hạn\nFILE: brief.pdf  " + "x" * 200, every="1h", script=BROKEN)
    rig = told(deps_factory(), named)

    await rig.sched.run_job(DUE)

    [(_, text)] = rig.notices
    first, *rest = text.split("\n")
    assert first.startswith('Lịch "Nhắc hạn FILE: brief.pdf xxx') and "…" in first
    assert len(rest) == 2 and rest[0] == WHY


@pytest.mark.parametrize("ended_by", ["", " \n "])
def test_a_run_nobody_said_what_ended_is_told_by_its_status_and_not_by_what_it_kept(ended_by):
    """What the run kept is what the script said, printed lines and all: the message is
    never made from it, not even for want of anything else."""
    job = Job(DUE, "default", due(BROKEN))
    run = RunRecord("r1", "default", None, f"job:{DUE}", NAME, FAILED, "2026-09-19T07:00:00")
    run.summary = "đã đọc 3 thư"
    run.steps = [{"kind": "tool", "name": "tool_script", "ok": False, "output": STEP}]

    assert failure_notice(job, run, ended_by) == notice(FAILED)


def test_what_ended_a_script_is_told_on_one_line():
    job = Job(DUE, "default", due(BROKEN))
    run = RunRecord("r1", "default", None, f"job:{DUE}", NAME, FAILED, "2026-09-19T07:00:00")

    assert failure_notice(job, run, "hai dòng\n  của một lỗi") == notice("hai dòng của một lỗi")


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
    assert (run.status, run.steps[0]["output"]) == (FAILED, STEP)
    assert rig.kept() == [run.to_dict()]


async def test_a_notice_that_never_returns_is_given_up_on_and_the_next_job_runs(
    deps_factory, caplog, monkeypatch
):
    """A chat on a line gone quiet answers nothing and closes nothing. The clock waits for
    the notice of one job before it runs the next, so a notice it waited on for ever would
    be the last thing it did until the server was started again."""
    monkeypatch.setattr(f"{LOGGER}.NOTICE_TIMEOUT_SECONDS", 0.05)
    asked: list[str] = []
    dropped: list[str] = []

    async def hangs(agent_id: str, text: str) -> bool:
        asked.append(agent_id)
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            dropped.append(agent_id)
            raise
        return True

    after = Schedule("after", "Việc sau", cron="0 7 * * *", script='print("xong")')
    rig = told(deps_factory(), due(BROKEN), after, notify=hangs)
    assert rig.sched.due() == []

    with caplog.at_level(logging.INFO, logger=LOGGER):
        runs = await asyncio.wait_for(rig.sched.tick(MORNING + timedelta(days=1)), timeout=30)

    # The job after the one whose notice hung ran, in the same round of the clock.
    [failed, later] = runs
    assert (later.source, later.status) == ("job:default/after", DONE)
    # The send was let go of, not left waiting behind the clock...
    assert asked == ["default"] and dropped == ["default"]
    # ...and is in the log as any notice that could not be sent is.
    [record] = [r for r in caplog.records if r.name == LOGGER]
    assert record.levelno == logging.ERROR and DUE in record.getMessage()
    assert record.exc_info is not None and isinstance(record.exc_info[1], TimeoutError)
    assert (failed.status, failed.steps[0]["output"]) == (FAILED, STEP)
    assert rig.kept() == [failed.to_dict()]
    assert [job["running"] for job in rig.sched.describe()] == [False, False]


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
    assert fake.sent == [notice(WHY)]


async def test_a_members_failed_script_is_told_under_the_members_name(crew, fake):
    with_schedules(crew.agents["coach"], due(BROKEN))
    runtime = runtime_of(crew)

    run = await runtime.scheduler.run_job("coach/due")

    assert (run.agent_id, run.status) == ("coach", FAILED)
    assert fake.sent == ["[HLV]\n" + notice(WHY)]


@pytest.mark.parametrize(("agent_id", "opening"), [("default", ""), ("coach", "[HLV]\n")])
async def test_a_notice_is_said_as_it_stands_and_attaches_nothing(crew, fake, agent_id, opening):
    """It quotes what a script said, which is whatever tools gave it. A line of that shaped
    like an attachment line stays in the sentence, and no file goes out."""
    text = attachable(crew)

    assert await crew.notify(agent_id, text) is True

    assert fake.sent == [opening + text] and fake.uploads == []
    assert "FILE: brief.pdf" in fake.sent[0] and "MEDIA: chart.png" in fake.sent[0]


async def test_a_notice_is_sent_as_every_message_of_the_bots_is_its_emphasis_marks_taken_off(
    make_channel, deps_factory, fake
):
    """The bot sends text with no parse mode, where the asterisks a name or an error was
    written with would show as they are. The two kinds it takes off every message it takes
    off this one, in the name and in the reason alike; an asterisk between two digits is
    no such mark, and stays."""
    source = 'raise ValueError("thiếu **cột ngày** ở sổ *chi* 2*3")'
    named = Schedule("due", "**Nhắc hạn** *gấp* 2*3", every="1h", script=source)
    deps = with_schedules(deps_factory(), named)
    runtime = runtime_of(make_channel(deps))

    run = await runtime.scheduler.run_job(DUE)

    told_as = notice(erred(1, "ValueError: thiếu cột ngày ở sổ chi 2*3"), "Nhắc hạn gấp 2*3")
    assert run.status == FAILED and fake.sent == [told_as]
    # The run keeps what the script said as it said it.
    assert "thiếu **cột ngày** ở sổ *chi* 2*3" in run.steps[0]["output"]


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
    assert fake.sent == [notice(WHY)]
    [run] = runtime.hub.recent(5, source=f"job:{DUE}")
    assert isinstance(run, RunRecord) and (run.status, run.conversation_id) == (FAILED, None)
    assert texts.TELEGRAM_RUN_UNFINISHED.format(reason=run.summary) not in fake.sent
