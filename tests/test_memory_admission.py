"""Memory admission: an agent with a memory budget has each line a rewrite adds screened
before the gate sees it, and a rewrite still over the budget waits for a person."""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import date

import pytest

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agents.profile_yaml import parse_profile
from my_agent_crew.llm.fake import completion
from my_agent_crew.memory import agent_store
from my_agent_crew.memory.admission import added_lines, verdicts
from my_agent_crew.memory.consolidate import consolidate_memory
from my_agent_crew.store.memory_proposals import APPROVED, PENDING

TODAY = date.today().isoformat()


@pytest.fixture
def hub(store) -> ActivityHub:
    return ActivityHub(store)


def test_a_budget_is_read_from_the_agents_own_file(tmp_path, settings):
    assert parse_profile("a", tmp_path, {}, settings).memory_budget_chars == 0
    profile = parse_profile("a", tmp_path, {"memory_budget_chars": 1500}, settings)
    assert profile.memory_budget_chars == 1500
    assert profile.to_dict()["memory_budget_chars"] == 1500
    for wrong in (True, -1, "1500", 1.5):
        with pytest.raises(ValueError, match="memory_budget_chars"):
            parse_profile("a", tmp_path, {"memory_budget_chars": wrong}, settings)


def test_only_lines_that_say_something_new_are_screened():
    previous = "- Sếp thích trà. (2026-10-01)\n- Đơn đang giao."
    new = "# Ghi nhớ\n- Sếp thích trà. (2026-10-29)\n- Đơn đang giao.\n- Ngủ trước 23h."
    assert added_lines(previous, new) == [3]


def test_a_line_the_reply_is_unclear_about_is_let_in():
    reply = "1. NHẬN\n2) bỏ: tra lại được trong sổ\n`3. BỎ`\n4. có lẽ\n9. BỎ: ngoài danh sách"
    assert verdicts(reply, 4) == {2: "tra lại được trong sổ", 3: texts.ADMISSION_NO_REASON}


def rewrite(deps_factory, before: str, replies: list[str], budget: int, autonomous=True):
    """Deps whose model answers the rewrite and then the screen with `replies`, over the
    memory `before` and a note newer than it, for an agent with `budget`."""
    deps = deps_factory(
        script=[completion(reply) for reply in replies], autonomous_default=autonomous
    )
    deps.profile = replace(deps.agent, memory_budget_chars=budget)
    path = deps.agent.memory_file
    agent_store.write_memory_md(path, before)
    agent_store.write_note(deps.agent.memory_dir, TODAY, "Cập nhật.")
    stamp = path.stat().st_mtime + 10
    os.utime(deps.agent.memory_dir / f"{TODAY}.md", (stamp, stamp))
    return deps


async def test_a_line_turned_away_never_reaches_memory(deps_factory, hub):
    after = f"- Sếp thích trà.\n- Đơn sách đang ở hải quan. ({TODAY})\n- Ngủ trước 23h. ({TODAY})"
    replies = [f"{after}\n---LÝ DO---\n- thêm hai dòng", "1. BỎ: tra lại được\n2. NHẬN"]
    deps = rewrite(deps_factory, "- Sếp thích trà.", replies, budget=2000)

    proposal = await consolidate_memory(deps, hub)
    assert proposal is not None and proposal.status == APPROVED
    kept = f"- Sếp thích trà.\n- Ngủ trước 23h. ({TODAY})"
    assert agent_store.read_memory_md(deps.agent.memory_file) == kept
    note = texts.ADMISSION_TURNED_AWAY.format(
        line=f"Đơn sách đang ở hải quan. ({TODAY})", why="tra lại được"
    )
    assert proposal.reasons == f"- thêm hai dòng\n{note}"
    # Both calls are steps of the rewrite's run, so its cost counts the screen too.
    assert len(hub.recent(1)[0].steps) == 2


async def test_without_a_budget_nothing_is_screened(deps_factory, hub):
    after = f"- Sếp thích trà.\n- Đơn sách đang ở hải quan. ({TODAY})"
    deps = rewrite(deps_factory, "- Sếp thích trà.", [after], budget=0)

    proposal = await consolidate_memory(deps, hub)
    assert proposal is not None and proposal.body == after
    sent = deps.chain.providers["scripted"].requests[0].messages[0].content
    assert "tối đa 24000 ký tự" in sent and "ngân sách" not in sent


async def test_the_rewrite_is_told_its_budget(deps_factory, hub):
    deps = rewrite(deps_factory, "- Sếp thích trà.", ["- Sếp thích trà."], budget=1500)

    await consolidate_memory(deps, hub)
    sent = deps.chain.providers["scripted"].requests[0].messages[0].content
    assert texts.CONSOLIDATE_BUDGET.format(budget=1500) in sent
    assert "tối đa 1500 ký tự" in sent


async def test_a_rewrite_over_budget_waits_for_the_person(deps_factory, hub):
    after = f"- Sếp thích trà.\n- Ngủ trước 23h, dậy lúc 6h mỗi ngày. ({TODAY})"
    deps = rewrite(deps_factory, "- Sếp thích trà.", [after, "1. NHẬN"], budget=30)

    proposal = await consolidate_memory(deps, hub)
    assert proposal is not None and proposal.status == PENDING
    why = texts.HELD_OVER_BUDGET.format(size=len(after), budget=30)
    assert hub.recent(1)[0].summary == texts.CONSOLIDATE_HELD.format(why=why)


async def test_a_screen_that_fails_keeps_the_new_lines(deps_factory, hub):
    after = f"- Sếp thích trà.\n- Ngủ trước 23h. ({TODAY})"
    deps = rewrite(deps_factory, "- Sếp thích trà.", [after], budget=2000)

    proposal = await consolidate_memory(deps, hub)  # the script has no reply for the screen
    assert proposal is not None and proposal.body == after
    assert proposal.reasons == texts.ADMISSION_FAILED
