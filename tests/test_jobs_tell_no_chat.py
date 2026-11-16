"""A scheduled job sends nothing to the chat, whatever its run comes to.

The web is where a job's report is read: its conversation, the inbox and the push
(`webpush/notices.py`). Telegram is a chat the person opens and nothing else, so a job that
answers, one whose script failed, one the day's cap skipped and a rewrite of memory held for
the person each leave their run on the jobs page and call no method of the bot's. Each job
here runs on a server's runtime with a bot that would send whatever it were handed.
"""

from __future__ import annotations

from datetime import UTC, datetime

from my_agent_crew import texts
from my_agent_crew.agents.profile import Schedule, consolidate_schedule
from my_agent_crew.llm.fake import completion
from my_agent_crew.store.memory_proposals import PENDING
from my_agent_crew.store.runs import DONE, FAILED, HALTED
from tests.test_job_failure_streaks import runtime_of
from tests.test_jobs_daily_cost_cap import skipped_by, spend
from tests.test_memory_validity import rewrite
from tests.test_scheduler import with_schedules

BRIEF = Schedule("brief", "Bản tin sáng", cron="0 7 * * *", prompt="tin gì mới")


async def test_a_prompt_jobs_answer_is_kept_for_the_web_and_sent_to_no_chat(
    make_channel, deps_factory, fake
):
    deps = with_schedules(deps_factory(script=[completion("Bản tin: trời đẹp.")]), BRIEF)
    runtime = runtime_of(make_channel(deps))

    run = await runtime.scheduler.run_job("default/brief")

    assert run.status == DONE
    assert deps.store.history(run.conversation_id)[-1].message.content == "Bản tin: trời đẹp."
    assert fake.calls == []


async def test_a_script_job_that_failed_is_counted_and_sent_to_no_chat(
    make_channel, deps_factory, fake
):
    due = Schedule("due", "Nhắc hạn", cron="0 7 * * *", script='raise ValueError("hỏng")')
    deps = with_schedules(deps_factory(), due)
    runtime = runtime_of(make_channel(deps))

    run = await runtime.scheduler.run_job("default/due")

    assert (run.status, run.conversation_id) == (FAILED, None)
    [row] = runtime.scheduler.describe()
    assert row["failing"]["count"] == 1
    assert fake.calls == []


async def test_a_job_the_days_cap_skipped_says_why_on_its_run_and_to_no_chat(
    make_channel, deps_factory, fake
):
    capped = deps_factory(script=[completion("Không có gì mới.")], jobs_daily_cost_cap_usd=1.0)
    deps = with_schedules(capped, BRIEF)
    spend(deps, 1.2, datetime.now(UTC))
    runtime = runtime_of(make_channel(deps))

    run = await runtime.scheduler.run_job("default/brief")

    assert (run.status, run.summary) == (HALTED, skipped_by(1.2))
    assert deps.chain.providers["scripted"].requests == []
    assert fake.calls == []


async def test_a_rewrite_of_memory_held_for_the_person_is_sent_to_no_chat(
    make_channel, deps_factory, fake
):
    deps = rewrite(deps_factory, "- Sếp thích trà.\n- Sếp ngủ trước 23h.", "- Sếp thích trà.")
    with_schedules(deps, consolidate_schedule("30 3 * * 0"))
    runtime = runtime_of(make_channel(deps))

    run = await runtime.scheduler.run_job("default/memory-consolidate")

    [proposal] = deps.store.proposals.list()
    assert (run.status, proposal.status) == (DONE, PENDING)
    held = texts.CONSOLIDATE_HELD.format(why=texts.HELD_REMOVED.format(count=1))
    assert run.summary.startswith(held)
    assert fake.calls == []
