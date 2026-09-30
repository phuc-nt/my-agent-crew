"""Pure logic behind memory hygiene: dated lines, the removed/invented-date gate, and the
consolidate integration that wires them into a proposal."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.llm.fake import completion
from my_agent_crew.memory import agent_store, fact_dates
from my_agent_crew.memory.consolidate import consolidate_memory
from my_agent_crew.store.memory_proposals import APPROVED, PENDING


def test_review_list_finds_undated_and_stale_lines_and_skips_the_rest():
    today = date(2026, 9, 30)
    memory = "\n".join(
        [
            "# MEMORY",
            "",
            "- Chưa có ngày nào cả.",
            "- Sếp thích trà. (2026-09-29)",
            "- Việc cũ hơn 90 ngày. (2026-06-01)",
            "  dòng thụt lề tiếp nối không phải bullet mới",
        ]
    )
    review = fact_dates.review_list(memory, today)
    assert review.undated == ["- Chưa có ngày nào cả."]
    assert review.stale == ["- Việc cũ hơn 90 ngày. (2026-06-01)"]
    assert review.more_undated == 0 and review.more_stale == 0


def test_review_list_ignores_headings_and_blank_lines():
    today = date(2026, 9, 30)
    memory = "# Tiêu đề\n\n\n- Còn mới, có ngày. (2026-09-28)\n"
    review = fact_dates.review_list(memory, today)
    assert review.undated == [] and review.stale == []


def test_review_list_caps_each_bucket_at_forty_and_counts_the_rest():
    today = date(2026, 9, 30)
    lines = [f"- Việc {i} không ngày." for i in range(45)]
    review = fact_dates.review_list("\n".join(lines), today)
    assert len(review.undated) == 40
    assert review.more_undated == 5
    assert review.more_stale == 0


def test_split_reasons_with_the_vietnamese_separator():
    text = "bộ nhớ mới\n- dòng 1\n---LÝ DO---\n- bỏ vì cũ\n- gộp hai dòng"
    body, reasons = fact_dates.split_reasons(text)
    assert body == "bộ nhớ mới\n- dòng 1"
    assert reasons == "- bỏ vì cũ\n- gộp hai dòng"


def test_split_reasons_accepts_the_lowercase_unaccented_marker():
    text = "bộ nhớ\n---ly do---\nlý do ở đây"
    body, reasons = fact_dates.split_reasons(text)
    assert body == "bộ nhớ" and reasons == "lý do ở đây"


def test_split_reasons_without_a_separator_keeps_the_whole_answer_as_the_body():
    text = "chỉ có bộ nhớ, không có lý do"
    body, reasons = fact_dates.split_reasons(text)
    assert body == text and reasons == ""


def test_split_reasons_runs_before_any_truncation_so_long_reasons_do_not_eat_the_body():
    body_text = "x" * 100
    reasons_text = "y" * 5000
    text = f"{body_text}\n---LÝ DO---\n{reasons_text}"
    body, reasons = fact_dates.split_reasons(text)
    assert body == body_text
    assert len(reasons) == 4000
    assert reasons == reasons_text[:4000]


def test_removed_lines_is_empty_when_the_text_is_identical():
    text = "- Sếp thích trà. (2026-09-20)\n- Sếp thích cà phê."
    assert fact_dates.removed_lines(text, text) == []


def test_removed_lines_is_empty_when_only_the_date_suffix_changes():
    previous = "- Sếp thích trà. (2026-06-01)"
    new = "- Sếp thích trà. (2026-09-29)"
    assert fact_dates.removed_lines(previous, new) == []


def test_removed_lines_is_empty_for_an_addition_only_rewrite():
    previous = "- Sếp thích trà."
    new = "- Sếp thích trà.\n- Sếp ngủ trước 23h. (2026-09-29)"
    assert fact_dates.removed_lines(previous, new) == []


def test_removed_lines_ignores_bullet_marker_whitespace_and_case_differences():
    previous = "-   Sếp Thích Trà.  "
    new = "* sếp thích trà."
    assert fact_dates.removed_lines(previous, new) == []


def test_removed_lines_catches_an_actual_drop():
    previous = "- Sếp thích trà.\n- Sếp ngủ trước 23h."
    new = "- Sếp thích trà."
    assert fact_dates.removed_lines(previous, new) == ["- Sếp ngủ trước 23h."]


def test_removed_lines_catches_a_rephrasing():
    previous = "- Sếp thích trà đen."
    new = "- Sếp thích trà xanh."
    assert fact_dates.removed_lines(previous, new) == ["- Sếp thích trà đen."]


def test_removed_lines_catches_a_negation_that_a_substring_match_would_miss():
    previous = "- Uống cà phê."
    new = "- Không uống cà phê."
    assert fact_dates.removed_lines(previous, new) == ["- Uống cà phê."]


def test_invented_dates_excludes_note_dates_today_and_dates_already_present():
    today = date(2026, 9, 30)
    previous = "- Việc cũ. (2026-06-01)"
    notes = [("2026-09-29", "ghi chép hôm qua")]
    new = "- Việc cũ. (2026-06-01)\n- Việc từ ghi chép. (2026-09-29)\n- Việc hôm nay. (2026-09-30)"
    assert fact_dates.invented_dates(previous, notes, new, today) == []


def test_invented_dates_catches_a_date_that_matches_none_of_the_allowed_sources():
    today = date(2026, 9, 30)
    previous = "- Việc cũ. (2026-06-01)"
    notes = [("2026-09-29", "ghi chép hôm qua")]
    new = "- Việc cũ. (2026-06-01)\n- Việc bịa ra. (2026-01-15)"
    assert fact_dates.invented_dates(previous, notes, new, today) == ["2026-01-15"]


def test_is_stale_true_past_the_threshold_false_within_it():
    today = date(2026, 9, 30)
    assert fact_dates.is_stale("2026-06-01T07:00:00", today) is True
    assert fact_dates.is_stale("2026-09-29T07:00:00", today) is False


def test_stale_facts_filters_by_the_updated_field():

    class Fake:
        def __init__(self, name: str, updated: str) -> None:
            self.name = name
            self.updated = updated

    today = date(2026, 9, 30)
    facts = [Fake("cu", "2026-06-01T07:00:00"), Fake("moi", "2026-09-29T07:00:00")]
    assert [f.name for f in fact_dates.stale_facts(facts, today)] == ["cu"]


# --- Integration with consolidate: the fake model returns a reasoned rewrite ---


def write_memory(deps, text: str) -> Path:
    path = deps.agent.memory_file
    agent_store.write_memory_md(path, text)
    return path


def write_note(deps, day: str, text: str, *, newer_than: Path | None = None) -> None:
    agent_store.write_note(deps.agent.memory_dir, day, text)
    if newer_than is not None:
        stamp = newer_than.stat().st_mtime + 10
        os.utime(deps.agent.memory_dir / f"{day}.md", (stamp, stamp))


@pytest.fixture
def hub(store) -> ActivityHub:
    return ActivityHub(store)


async def test_consolidate_stores_reasons_and_the_prompt_carries_the_review_list_and_today(
    deps_factory, hub
):
    reply = "- Sếp thích trà. (2026-09-30)\n---LÝ DO---\n- Giữ nguyên, chỉ cập nhật ngày."
    deps = deps_factory(script=[completion(reply)])
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-30", "Sếp thích trà.", newer_than=memory)

    proposal = await consolidate_memory(deps, hub)
    assert proposal is not None
    assert proposal.reasons == "- Giữ nguyên, chỉ cập nhật ngày."
    assert proposal.body == "- Sếp thích trà. (2026-09-30)"

    provider = deps.chain.providers["scripted"]
    sent = provider.requests[0].messages[0].content
    assert "- Sếp thích trà." in sent  # the undated line is fed back for review
    assert "2026-09-30" in sent  # today's date is in the prompt


async def test_a_rewrite_identical_to_the_current_text_is_unchanged_even_with_reasons(
    deps_factory, hub
):
    reply = "- Sếp thích trà.\n---LÝ DO---\n- Không có gì để đổi."
    deps = deps_factory(script=[completion(reply)])
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Sếp thích trà.", newer_than=memory)

    assert await consolidate_memory(deps, hub) is None
    assert hub.recent(5)[0].summary == texts.CONSOLIDATE_UNCHANGED
    assert deps.store.proposals.list() == []


# --- The gate: a rewrite that drops or rephrases a line never auto-applies ---


async def test_an_autonomous_agent_with_a_dropped_line_stays_pending_and_leaves_the_file(
    deps_factory, hub
):
    reply = "- Sếp thích trà.\n---LÝ DO---\n- Bỏ dòng ngủ vì không còn đúng."
    deps = deps_factory(script=[completion(reply)], autonomous_default=True)
    memory = write_memory(deps, "- Sếp thích trà.\n- Sếp ngủ trước 23h.")
    write_note(deps, "2026-09-19", "Cập nhật.", newer_than=memory)

    proposal = await consolidate_memory(deps, hub)
    assert proposal is not None and proposal.status == PENDING
    assert agent_store.read_memory_md(memory) == "- Sếp thích trà.\n- Sếp ngủ trước 23h."
    run = hub.recent(5)[0]
    assert run.summary.startswith(texts.CONSOLIDATE_PROPOSED_REMOVING.split("{")[0])


async def test_an_autonomous_agent_with_only_an_addition_still_auto_applies(deps_factory, hub):
    reply = "- Sếp thích trà.\n- Sếp ngủ trước 23h. (2026-09-19)\n---LÝ DO---\n- Thêm từ ghi chép."
    deps = deps_factory(script=[completion(reply)], autonomous_default=True)
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Sếp ngủ trước 23h.", newer_than=memory)

    proposal = await consolidate_memory(deps, hub)
    assert proposal is not None and proposal.status == APPROVED
    assert agent_store.read_memory_md(memory) == (
        "- Sếp thích trà.\n- Sếp ngủ trước 23h. (2026-09-19)"
    )


async def test_an_autonomous_agent_with_only_a_date_change_still_auto_applies(deps_factory, hub):
    reply = "- Sếp thích trà. (2026-09-19)\n---LÝ DO---\n- Cập nhật ngày xác nhận."
    deps = deps_factory(script=[completion(reply)], autonomous_default=True)
    memory = write_memory(deps, "- Sếp thích trà. (2026-06-01)")
    write_note(deps, "2026-09-19", "Sếp thích trà.", newer_than=memory)

    proposal = await consolidate_memory(deps, hub)
    assert proposal is not None and proposal.status == APPROVED


async def test_a_rewrite_with_an_invented_date_stays_pending_and_names_the_date(deps_factory, hub):
    reply = "- Sếp thích trà.\n- Việc bịa ra. (2026-01-15)\n---LÝ DO---\n- Thêm một việc mới."
    deps = deps_factory(script=[completion(reply)], autonomous_default=True)
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Cập nhật.", newer_than=memory)

    proposal = await consolidate_memory(deps, hub)
    assert proposal is not None and proposal.status == PENDING
    assert "2026-01-15" in proposal.reasons
    assert agent_store.read_memory_md(memory) == "- Sếp thích trà."
