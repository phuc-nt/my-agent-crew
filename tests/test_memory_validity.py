"""Memory lines that hold only until a known day: how the end day is read, when a line
leaves the prompt, and what the rewrite gate makes of end days coming and going."""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agents.context import bootstrap_sections
from my_agent_crew.llm.fake import completion
from my_agent_crew.memory import agent_store, fact_dates
from my_agent_crew.memory.consolidate import consolidate_memory
from my_agent_crew.memory.line_validity import cut_short, drop_expired
from my_agent_crew.store.memory_proposals import APPROVED, PENDING

TODAY = date(2026, 10, 29)


def day(offset: int) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


@pytest.fixture
def hub(store) -> ActivityHub:
    return ActivityHub(store)


def test_an_end_day_follows_the_date_after_an_arrow_either_way_it_is_typed():
    assert fact_dates.until_day("- Đơn đang giao. (2026-10-28 → 2026-11-02)") == date(2026, 11, 2)
    assert fact_dates.until_day("- Đơn đang giao. (2026-10-28->2026-11-02)") == date(2026, 11, 2)
    assert fact_dates.until_day("- Sếp thích trà. (2026-10-28)") is None
    # Not a real day: the line keeps being said rather than vanish on a typo.
    assert fact_dates.until_day("- Đơn đang giao. (2026-10-28 → 2026-02-30)") is None


def test_the_end_day_does_not_change_what_a_line_says_or_when_it_was_seen():
    with_end = "- Đơn đang giao. (2026-10-28 → 2026-11-02)"
    assert fact_dates.line_key(with_end) == fact_dates.line_key("- Đơn đang giao.")
    assert fact_dates.invented_dates("", [("2026-10-28", "ghi chép")], with_end, TODAY) == []


def test_a_line_holds_through_its_last_day_and_leaves_the_day_after():
    memory = "- Sếp thích trà.\n- Đơn đang giao. (2026-10-20 → 2026-10-29)"
    assert drop_expired(memory, TODAY) == memory
    assert drop_expired(memory, TODAY + timedelta(days=1)) == "- Sếp thích trà."


def test_review_lists_a_line_past_its_end_day_only_as_expired():
    memory = "- Chuyến đi Đà Lạt. (2026-10-01 → 2026-10-05)\n- Chưa có ngày."
    review = fact_dates.review_list(memory, TODAY)
    assert review.expired == ["- Chuyến đi Đà Lạt. (2026-10-01 → 2026-10-05)"]
    assert review.undated == ["- Chưa có ngày."] and review.stale == []


def test_an_end_day_given_to_a_line_already_there_is_a_cut():
    previous = "- Gói nhạc còn hạn. (2026-10-01)\n- Đơn đang giao. (2026-10-28 → 2026-11-09)"
    new = "\n".join(
        [
            "- Gói nhạc còn hạn. (2026-10-01 → 2026-11-01)",  # end day where there was none
            "- Đơn đang giao. (2026-10-28 → 2026-11-12)",  # later: not a cut
            "- Vé tàu ngày 5. (2026-10-28 → 2026-11-05)",  # new line: nothing lost
        ]
    )
    assert cut_short(previous, new) == ["- Gói nhạc còn hạn. (2026-10-01 → 2026-11-01)"]


def test_the_prompt_leaves_out_what_has_stopped_holding(deps_factory):
    deps = deps_factory(script=[])
    agent_store.write_memory_md(
        deps.agent.memory_file,
        f"- Sếp thích trà.\n- Đơn đã giao xong. ({day(-9)} → {day(-2)})\n"
        f"- Đơn đang giao. ({day(-1)} → {day(3)})",
    )
    memory = dict(bootstrap_sections(deps.agent))["MEMORY.md"]
    assert "Đơn đã giao xong" not in memory
    assert "Sếp thích trà." in memory and "Đơn đang giao." in memory


def rewrite(deps_factory, before: str, after: str, *, autonomous: bool = True):
    """Deps whose model answers with `after`, over the memory `before` and a note newer
    than it."""
    reply = completion(f"{after}\n---LÝ DO---\n- x")
    deps = deps_factory(script=[reply], autonomous_default=autonomous)
    path = deps.agent.memory_file
    agent_store.write_memory_md(path, before)
    agent_store.write_note(deps.agent.memory_dir, day(0), "Cập nhật.")
    stamp = path.stat().st_mtime + 10
    os.utime(deps.agent.memory_dir / f"{day(0)}.md", (stamp, stamp))
    return deps


async def test_dropping_a_line_past_its_end_day_needs_no_one(deps_factory, hub):
    before = f"- Sếp thích trà.\n- Đơn đã giao. ({day(-9)} → {day(-2)})"
    deps = rewrite(deps_factory, before, "- Sếp thích trà.")

    proposal = await consolidate_memory(deps, hub)
    assert proposal is not None and proposal.status == APPROVED
    assert agent_store.read_memory_md(deps.agent.memory_file) == "- Sếp thích trà."


async def test_a_new_line_that_will_end_needs_no_one(deps_factory, hub):
    after = f"- Sếp thích trà.\n- Đơn đang giao. ({day(0)} → {day(5)})"
    deps = rewrite(deps_factory, "- Sếp thích trà.", after)

    proposal = await consolidate_memory(deps, hub)
    assert proposal is not None and proposal.status == APPROVED


async def test_ending_a_line_already_there_waits_for_the_person(deps_factory, hub):
    before, after = f"- Sếp thích trà. ({day(-3)})", f"- Sếp thích trà. ({day(-3)} → {day(1)})"
    deps = rewrite(deps_factory, before, after)

    proposal = await consolidate_memory(deps, hub)
    assert proposal is not None and proposal.status == PENDING
    held = texts.CONSOLIDATE_HELD.format(why=texts.HELD_REMOVED.format(count=1))
    assert hub.recent(5)[0].summary == held


async def test_the_rewrite_is_asked_to_drop_what_has_ended(deps_factory, hub):
    ended = f"- Đơn đã giao. ({day(-9)} → {day(-2)})"
    deps = rewrite(deps_factory, f"- Sếp thích trà.\n{ended}", "- Sếp thích trà.", autonomous=False)

    await consolidate_memory(deps, hub)
    sent = deps.chain.providers["scripted"].requests[0].messages[0].content
    assert f"--- dòng đã qua ngày cuối ---\n{ended}" in sent
