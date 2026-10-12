"""What the run of a job that asked no model is summed up by, and how a cut of it shows.

A run's summary is one short text: on its card, on the "last run" line of the jobs list and
in the list of what needs the person. A job that asked no model has no answer to be summed
up by. A command job, and a script that ended well, are summed up by the end of what they
said, where the result is: whole while it is short, and past that behind the mark of a cut,
so that no summary opens in the middle of a word with nothing saying so. A script that
failed is summed up by what ended it, from its start and on one line, cut as any preview is:
the end of all it said opened in the middle of the sentence that says why. Where nothing
says what ended it, it is summed up by that end still, marked. And an upkeep run that failed
(the rewrite of `MEMORY.md`, the wiki compile) is summed up by the start of its error, cut
with the same mark. Every script here runs in a real child process.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from my_agent_crew.activity import ActivityHub
from my_agent_crew.agents.profile import Schedule
from my_agent_crew.llm.provider import ProviderError
from my_agent_crew.memory.consolidate import consolidate_memory
from my_agent_crew.memory.wiki_compile import compile_wiki
from my_agent_crew.scheduler import Scheduler, script_job
from my_agent_crew.scheduler.jobs import ending
from my_agent_crew.script.tool import Ran
from my_agent_crew.store.runs import DONE, FAILED, RunRecord
from my_agent_crew.tools.result import ToolResult
from my_agent_crew.tools.shell import SHELL_TOOL_NAME
from tests.test_memory_consolidate import write_memory, write_note
from tests.test_scheduler import with_schedules
from tests.test_script_gate import ASK_LIST, PUSH, SECRET, agent, shelled
from tests.test_script_job import THEN, crew
from tests.test_script_job_gate import DUE, scheduled
from tests.test_script_tool import erred, halted, unfinished

# What a summary keeps, and the mark that stands where it left the rest out.
KEPT, CUT = 160, "…"
MUCH = "đầu " + "x" * 400
LONG_ERROR = "mở đầu " + "x" * 300 + " kết"


@pytest.fixture
def hub(store) -> ActivityHub:
    return ActivityHub(store)


def one_line(text: str) -> str:
    return " ".join(text.split())


# --- the end of what was said ---


@pytest.mark.parametrize(
    "said",
    ["", "synced", "x" * KEPT, "hai dòng\ncủa một việc"],
    ids=["nothing", "a word", "all a summary keeps", "two lines"],
)
def test_a_text_within_what_a_summary_keeps_is_summed_up_whole_and_unmarked(said):
    assert ending(said) == said
    # Judged by what is left of it once the blank around it is gone, as it is kept.
    assert ending(" " * 300 + f"\n{said} \n") == said


def test_a_longer_text_is_summed_up_by_its_end_behind_the_mark_of_a_cut():
    said = f"{MUCH} cuối: HP3-12 còn 14 ngày"

    assert ending(said) == CUT + said[-KEPT:]
    assert ending(said).endswith("cuối: HP3-12 còn 14 ngày") and "đầu" not in ending(said)
    # One character past what is kept is a cut already.
    assert ending("a" + "b" * KEPT) == CUT + "b" * KEPT


@pytest.mark.parametrize(("code", "status"), [(0, DONE), (3, FAILED)])
async def test_a_command_job_that_said_much_is_summed_up_by_its_marked_end(
    deps_factory, hub, code, status
):
    said = f"{MUCH} cuối: đã đồng bộ 14 thư"
    job = Schedule("sync", "Đồng bộ", every="1h", command=f"echo '{said}'; exit {code}")
    deps = with_schedules(deps_factory(), job)
    sched = Scheduler({"default": deps}, hub, clock=lambda: datetime(2026, 9, 19, 8, 0))

    run = await sched.run_job("default/sync")

    assert (run.status, run.summary) == (status, CUT + said[-KEPT:])


async def test_a_script_that_ended_well_and_printed_much_is_summed_up_by_its_marked_end(
    deps_factory,
):
    rig = crew(deps_factory, f'print("{MUCH}")\nprint("cuối: HP3-12 còn 14 ngày")')

    run = await rig.due()

    printed = f"{MUCH}\ncuối: HP3-12 còn 14 ngày"
    assert (run.status, run.summary) == (DONE, CUT + printed[-KEPT:])


# --- a script that failed ---


async def test_what_ended_a_script_at_length_is_summed_up_from_its_start_as_a_preview_is_cut(
    deps_factory,
):
    source = 'print("in trước")\nraise ValueError("mở đầu " + "x" * 700 + " việc cần làm")'
    rig = crew(deps_factory, source, THEN)

    run = await rig.due()

    whole = erred(2, "ValueError: mở đầu " + "x" * 700 + " việc cần làm")
    assert (run.status, run.summary) == (FAILED, whole[:KEPT] + CUT)
    assert run.summary.startswith("Lỗi ở dòng 2: ValueError: mở đầu xxx")


async def test_a_script_the_gate_ended_is_summed_up_from_the_start_of_the_refusal(deps_factory):
    """The refusal ends on what to do about it and is longer than a summary keeps: its end
    alone opened in the middle of the sentence that says why the script was ended."""
    deps, shell = agent(deps_factory)
    sched = scheduled(deps, shelled(PUSH))

    run = await sched.run_job(DUE)

    why = one_line(halted(3, ASK_LIST.format(name=SHELL_TOOL_NAME, pattern="--force")))
    assert len(why) > KEPT and shell.ran == []
    assert (run.status, run.summary) == (FAILED, why[:KEPT] + CUT)
    assert run.summary.startswith("Dừng ở dòng 3: ") and "trước" not in run.summary
    assert SECRET not in run.summary


async def test_what_ended_a_script_is_summed_up_on_one_line(deps_factory):
    rig = crew(deps_factory, 'raise ValueError("hai dòng\\n  của một lỗi")')

    run = await rig.due()

    assert run.summary == erred(1, "ValueError: hai dòng của một lỗi")


@pytest.mark.parametrize("ended_by", ["", " \n "])
@pytest.mark.parametrize(
    ("said", "summed_up"),
    [
        (unfinished("đã đọc 3 thư"), unfinished("đã đọc 3 thư")),
        (unfinished(MUCH, "cuối: không rõ vì sao"), CUT + f"{MUCH}\ncuối: không rõ vì sao"[-KEPT:]),
    ],
    ids=["short", "long"],
)
async def test_a_failed_script_nothing_says_what_ended_is_summed_up_by_the_end_of_what_it_said(
    deps_factory, monkeypatch, ended_by, said, summed_up
):
    async def ends_unsaid(*args: Any, **kwargs: Any) -> Ran:
        return Ran(ToolResult(ok=False, output=said), "", ended_by)

    monkeypatch.setattr(script_job, "run_source", ends_unsaid)
    rig = crew(deps_factory, 'print("có việc")', THEN)

    run = await rig.due()

    assert (run.status, run.summary) == (FAILED, summed_up)


# --- upkeep that failed ---

# What the provider said, and whether a summary has room for all the run failed with.
ERRORS = [
    pytest.param("hết hạn mức", True, id="short"),
    pytest.param(LONG_ERROR, False, id="long"),
    pytest.param("hai dòng\n  của một lỗi", True, id="two lines"),
]


def summed_up_by_its_start(run: RunRecord, failed: Exception, error: str, roomy: bool) -> None:
    """The run is summed up by the start of what it failed with: on one line, whole where
    there is room for it, and otherwise cut where a summary ends with the mark of the cut."""
    said = one_line(str(failed))
    assert said.endswith(one_line(error)) and (len(said) <= KEPT) is roomy
    assert (run.status, run.summary) == (FAILED, said if roomy else said[:KEPT] + CUT)


@pytest.mark.parametrize(("error", "roomy"), ERRORS)
async def test_a_rewrite_of_memory_that_failed_is_summed_up_by_the_start_of_its_error(
    deps_factory, hub, error, roomy
):
    deps = deps_factory(script=[ProviderError(error)])
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Sếp ngủ trước 23h.", newer_than=memory)

    with pytest.raises(ProviderError) as raised:
        await consolidate_memory(deps, hub)

    [run] = hub.recent(5)
    summed_up_by_its_start(run, raised.value, error, roomy)


@pytest.mark.parametrize(("error", "roomy"), ERRORS)
async def test_a_wiki_compile_that_failed_is_summed_up_by_the_start_of_its_error(
    deps_factory, hub, error, roomy
):
    deps = deps_factory(script=[ProviderError(error)])
    write_note(deps, "2026-09-19", "Hạn Eco dời sang thứ tư.")

    with pytest.raises(ProviderError) as raised:
        await compile_wiki(deps, hub)

    [run] = hub.recent(5)
    summed_up_by_its_start(run, raised.value, error, roomy)
