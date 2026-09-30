"""Reviewing the shared user facts alongside a memory rewrite: a second model call, made
only for the master and only when there is at least one fact, whose output always waits
for approval no matter how the agent is configured."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from my_agent_crew import texts
from my_agent_crew.activity import ActivityHub
from my_agent_crew.agents.profile import WORK
from my_agent_crew.config import Route
from my_agent_crew.llm.fake import completion
from my_agent_crew.llm.types import TextDelta
from my_agent_crew.memory import agent_store, consolidate, fact_review, user_store
from my_agent_crew.memory.consolidate import consolidate_memory
from my_agent_crew.memory.fact_review import FactReview, review_user_facts
from my_agent_crew.store.memory_proposals import PENDING, SUPERSEDED, USER_FACT, USER_FORGET

REWRITE_REPLY = "- Sếp thích trà.\n---LÝ DO---\n- Không có gì để đổi."


def write_memory(deps, text: str) -> Path:
    path = deps.agent.memory_file
    agent_store.write_memory_md(path, text)
    return path


def write_note(deps, day: str, text: str, *, newer_than: Path | None = None) -> None:
    agent_store.write_note(deps.agent.memory_dir, day, text)
    if newer_than is not None:
        stamp = newer_than.stat().st_mtime + 10
        os.utime(deps.agent.memory_dir / f"{day}.md", (stamp, stamp))


def write_fact(deps, name: str, **overrides):
    fields = {
        "description": name,
        "type": "preference",
        "body": "thân fact",
        "written_by": "owner",
        "source": "chat",
        **overrides,
    }
    return user_store.write_fact(deps.settings.user_dir, name, **fields)


def non_master(deps, agent_id: str = "coach"):
    return replace(deps, profile=replace(deps.profile, id=agent_id, name=agent_id, mode=WORK))


def prompt_sent(deps, index: int) -> str:
    return deps.chain.providers["scripted"].requests[index].messages[0].content


def fact_line(prompt: str, name: str) -> str:
    return next(line for line in prompt.splitlines() if line.startswith(f"- {name} ("))


@pytest.fixture
def hub(store) -> ActivityHub:
    return ActivityHub(store)


# --- review_user_facts: the pure function, given facts directly ---


async def test_forget_and_update_actions_become_pending_proposals(deps_factory):
    json_reply = (
        '[{"action": "forget", "name": "ngu-som", "reason": "đã đổi thói quen"},'
        ' {"action": "update", "name": "tra", "body": "Sếp thích trà xanh.",'
        ' "reason": "ghi chép mới"}]'
    )
    deps = deps_factory(script=[completion(json_reply)])
    facts = [
        write_fact(deps, "ngu-som", description="Ngủ sớm", body="Ngủ trước 23h."),
        write_fact(deps, "tra", description="Thích trà", body="Sếp thích trà đen."),
    ]

    review = await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))
    assert review.created == 2 and review.skipped == 0 and not review.errored

    proposals = deps.store.proposals.list(status=PENDING)
    kinds = {p.name: p.kind for p in proposals}
    assert kinds == {"ngu-som": USER_FORGET, "tra": USER_FACT}
    forgotten = next(p for p in proposals if p.name == "ngu-som")
    assert forgotten.body == "Ngủ trước 23h."  # the card shows what approving would forget
    updated = next(p for p in proposals if p.name == "tra")
    assert updated.body == "Sếp thích trà xanh."
    assert updated.description == "Thích trà"  # kept from the existing fact, not the model
    assert updated.type == "preference"
    assert updated.reasons == "ghi chép mới"


async def test_stale_facts_come_first_oldest_first_then_the_rest_newest_first(deps_factory):
    deps = deps_factory(script=[completion("[]")])
    facts = [
        write_fact(deps, "moi-vua", now=datetime(2026, 9, 10, 8)),
        write_fact(deps, "cu-vua", now=datetime(2026, 5, 1, 8)),
        write_fact(deps, "moi-nhat", now=datetime(2026, 9, 29, 8)),
        write_fact(deps, "cu-nhat", now=datetime(2026, 3, 1, 8)),
    ]

    review = await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))
    assert review == FactReview()  # an empty array means nothing to do, not a broken reply

    sent = prompt_sent(deps, 0)
    shown = [sent.index(f"- {name} (") for name in ("cu-nhat", "cu-vua", "moi-nhat", "moi-vua")]
    assert shown == sorted(shown)


async def test_a_fact_whose_date_does_not_parse_sorts_as_the_oldest(deps_factory):
    deps = deps_factory(script=[completion("[]")])
    dated = write_fact(deps, "cu", now=datetime(2026, 3, 1, 8))
    undated = replace(write_fact(deps, "khong-ngay"), updated="")

    await review_user_facts(deps, [dated, undated], notes="", today=date(2026, 9, 30))

    sent = prompt_sent(deps, 0)
    assert sent.index("- khong-ngay (") < sent.index("- cu (")


async def test_only_sixty_facts_are_shown_and_a_name_past_the_cut_is_skipped(deps_factory):
    reply = '[{"action": "forget", "name": "f-60", "reason": "r"}]'
    deps = deps_factory(script=[completion(reply)])
    newest = datetime(2026, 9, 29, 12)
    facts = [write_fact(deps, f"f-{i:02d}", now=newest - timedelta(hours=i)) for i in range(61)]

    review = await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))
    assert review.created == 0 and review.skipped == 1
    assert deps.store.proposals.list(status=PENDING) == []

    sent = prompt_sent(deps, 0)
    assert "- f-59 (" in sent and "- f-60 (" not in sent
    assert texts.FACT_REVIEW_MORE.format(count=1) in sent


async def test_a_fact_line_carries_its_description_and_a_flattened_body_cut_at_400(deps_factory):
    deps = deps_factory(script=[completion("[]")])
    body = "dòng một\ndòng hai " + "x" * 500
    day = datetime(2026, 9, 20)
    facts = [write_fact(deps, "dai", description="Mô tả riêng", body=body, now=day)]

    await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))

    expected_body = ("dòng một dòng hai " + "x" * 500)[:400]
    expected = f"- dai (2026-09-20) — Mô tả riêng: {expected_body}"
    assert fact_line(prompt_sent(deps, 0), "dai") == expected


@pytest.mark.parametrize(
    "reply",
    [
        'Kết quả:\n```json\n[{"action": "forget", "name": "a", "reason": "r"}]\n```',
        'Xem [ghi chú] trước, rồi: [{"action": "forget", "name": "a", "reason": "r"}] hết.',
        '[{"action": "forget", "name": "a", "reason": "r"}, "không phải object", 3]',
    ],
)
async def test_the_first_json_array_is_read_out_of_prose_a_fence_or_stray_items(
    deps_factory, reply
):
    deps = deps_factory(script=[completion(reply)])
    facts = [write_fact(deps, "a")]

    review = await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))
    assert review == FactReview(created=1)


async def test_a_long_reason_is_cut_at_300_characters(deps_factory):
    reply = json.dumps([{"action": "forget", "name": "a", "reason": "l" * 350}])
    deps = deps_factory(script=[completion(reply)])
    facts = [write_fact(deps, "a")]

    await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))
    assert [p.reasons for p in deps.store.proposals.list(status=PENDING)] == ["l" * 300]


async def test_an_unknown_name_is_skipped(deps_factory):
    json_reply = '[{"action": "forget", "name": "khong-ton-tai", "reason": "lạ"}]'
    deps = deps_factory(script=[completion(json_reply)])
    facts = [write_fact(deps, "ton-tai")]

    review = await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))
    assert review.created == 0 and review.skipped == 1
    assert deps.store.proposals.list(status=PENDING) == []


async def test_an_action_other_than_forget_or_update_is_skipped(deps_factory):
    json_reply = '[{"action": "keep", "name": "a", "reason": "vẫn đúng"}, {"name": "a"}]'
    deps = deps_factory(script=[completion(json_reply)])
    facts = [write_fact(deps, "a")]

    review = await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))
    assert review.created == 0 and review.skipped == 2
    assert deps.store.proposals.list(status=PENDING) == []


async def test_an_update_with_no_body_or_an_unchanged_body_is_skipped(deps_factory):
    json_reply = (
        '[{"action": "update", "name": "a", "body": "", "reason": "rỗng"},'
        ' {"action": "update", "name": "b", "body": "y hệt thân hiện tại", "reason": "trùng"}]'
    )
    deps = deps_factory(script=[completion(json_reply)])
    facts = [
        write_fact(deps, "a", body="thân a"),
        write_fact(deps, "b", body="y hệt thân hiện tại"),
    ]

    review = await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))
    assert review.created == 0 and review.skipped == 2


async def test_more_than_ten_actions_are_truncated(deps_factory):
    actions = ",".join(f'{{"action": "forget", "name": "f{i}", "reason": "r"}}' for i in range(12))
    deps = deps_factory(script=[completion(f"[{actions}]")])
    facts = [write_fact(deps, f"f{i}") for i in range(12)]

    review = await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))
    assert review.created == 10


async def test_broken_json_creates_no_proposals_and_is_reported_as_an_error(deps_factory):
    deps = deps_factory(script=[completion("không phải JSON gì cả")])
    facts = [write_fact(deps, "a")]

    review = await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))
    assert review.created == 0 and review.errored is True
    assert deps.store.proposals.list(status=PENDING) == []


class CutShortProvider:
    """A stream that stops after its first chunk without ever delivering the answer."""

    name = "cut-short"

    async def stream(self, messages, tools, model, reasoning=""):
        yield TextDelta("[")


async def test_a_reply_that_never_arrives_is_reported_as_an_error(deps_factory):
    deps = deps_factory(
        providers={"cut-short": CutShortProvider()}, routes=(Route("cut-short", "m"),)
    )
    facts = [write_fact(deps, "a")]

    review = await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))
    assert review == FactReview(errored=True)


async def test_each_review_call_records_a_side_call_with_purpose_consolidate(deps_factory):
    deps = deps_factory(script=[completion('[{"action": "forget", "name": "a", "reason": "x"}]')])
    facts = [write_fact(deps, "a")]

    await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))
    rows = deps.store._conn.execute(
        "SELECT purpose FROM side_calls WHERE purpose = 'consolidate'"
    ).fetchall()
    assert len(rows) == 1


# --- Wired into consolidate_memory: master + facts, autonomy, dedupe ---


async def test_master_with_facts_gets_pending_proposals_even_when_autonomous(deps_factory, hub):
    json_reply = '[{"action": "forget", "name": "ngu-som", "reason": "đã đổi"}]'
    deps = deps_factory(
        script=[completion(REWRITE_REPLY), completion(json_reply)], autonomous_default=True
    )
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Cập nhật.", newer_than=memory)
    write_fact(deps, "ngu-som", description="Ngủ sớm", body="Ngủ trước 23h.")

    await consolidate_memory(deps, hub)

    fact_proposals = deps.store.proposals.list(status=PENDING)
    assert any(p.kind == USER_FORGET and p.status == PENDING for p in fact_proposals)


async def test_a_non_master_agent_makes_no_second_model_call(deps_factory, hub):
    deps = deps_factory(script=[completion(REWRITE_REPLY)])
    write_fact(deps, "ngu-som", description="Ngủ sớm", body="Ngủ trước 23h.")
    child = non_master(deps)
    memory = write_memory(child, "- Việc của coach.")
    write_note(child, "2026-09-19", "Cập nhật.", newer_than=memory)

    await consolidate_memory(child, hub)

    # A second call would be recorded even though the one-entry script cannot answer it, and
    # its failure would be caught and appended to the summary rather than raised.
    assert len(deps.chain.providers["scripted"].requests) == 1
    assert hub.recent(5)[0].summary == texts.CONSOLIDATE_PROPOSED


async def test_fact_review_still_runs_when_the_rewrite_step_is_unchanged(deps_factory, hub):
    json_reply = '[{"action": "forget", "name": "ngu-som", "reason": "đã đổi"}]'
    unchanged_reply = "- Sếp thích trà.\n---LÝ DO---\n- Không đổi gì."
    deps = deps_factory(script=[completion(unchanged_reply), completion(json_reply)])
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Sếp thích trà.", newer_than=memory)
    write_fact(deps, "ngu-som", description="Ngủ sớm", body="Ngủ trước 23h.")

    await consolidate_memory(deps, hub)

    assert any(p.kind == USER_FORGET for p in deps.store.proposals.list(status=PENDING))


async def test_a_fact_review_error_does_not_lose_the_rewrite_proposal(deps_factory, hub):
    changed_reply = "- Sếp thích trà.\n- Sếp thích cà phê.\n---LÝ DO---\n- Ghi thêm."
    deps = deps_factory(script=[completion(changed_reply), completion("JSON hỏng")])
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Cập nhật.", newer_than=memory)
    write_fact(deps, "ngu-som", description="Ngủ sớm", body="Ngủ trước 23h.")

    proposal = await consolidate_memory(deps, hub)
    assert proposal is not None


async def test_an_identical_pending_proposal_is_not_duplicated(deps_factory):
    json_reply = '[{"action": "forget", "name": "a", "reason": "r"}]'
    deps = deps_factory(script=[completion(json_reply), completion(json_reply)])
    facts = [write_fact(deps, "a")]

    await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))
    [first] = deps.store.proposals.list(status=None)
    again = await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))

    assert again == FactReview(skipped=1)
    # The card already waiting stays as it is, not replaced by an identical new one.
    everything = deps.store.proposals.list(status=None)
    assert [(p.id, p.status) for p in everything] == [(first.id, PENDING)]


async def test_a_different_body_supersedes_the_old_pending_hygiene_proposal(deps_factory):
    first = '[{"action": "update", "name": "a", "body": "thân một", "reason": "r1"}]'
    second = '[{"action": "update", "name": "a", "body": "thân hai", "reason": "r2"}]'
    deps = deps_factory(script=[completion(first), completion(second)])
    facts = [write_fact(deps, "a", body="thân gốc")]

    await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))
    await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))

    all_proposals = deps.store.proposals.list(status=None)
    pending = [p for p in all_proposals if p.status == PENDING]
    assert len(pending) == 1 and pending[0].body == "thân hai"
    superseded = [p for p in all_proposals if p.status == "superseded"]
    assert len(superseded) == 1 and superseded[0].body == "thân một"


async def test_a_forget_supersedes_a_pending_update_of_the_same_fact(deps_factory):
    first = '[{"action": "update", "name": "a", "body": "thân mới", "reason": "r1"}]'
    second = '[{"action": "forget", "name": "a", "reason": "r2"}]'
    deps = deps_factory(script=[completion(first), completion(second)])
    facts = [write_fact(deps, "a", body="thân gốc")]
    from_chat = deps.store.proposals.create(
        agent_id=deps.agent.id, kind=USER_FACT, name="a", body="ghi trong chat", source="chat"
    )

    await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))
    await review_user_facts(deps, facts, notes="", today=date(2026, 9, 30))

    everything = deps.store.proposals.list(status=None)
    hygiene = [(p.kind, p.status) for p in everything if p.source == fact_review.SOURCE]
    assert hygiene == [(USER_FORGET, PENDING), (USER_FACT, SUPERSEDED)]
    # A proposal from somewhere else is not the review's to replace.
    assert next(p for p in everything if p.id == from_chat.id).status == PENDING


# --- What the consolidation run reports, and what the review reads ---


async def test_the_run_summary_counts_the_fact_proposals(deps_factory, hub):
    json_reply = (
        '[{"action": "forget", "name": "ngu-som", "reason": "đã đổi"},'
        ' {"action": "forget", "name": "tra-den", "reason": "đã bỏ"}]'
    )
    deps = deps_factory(script=[completion(REWRITE_REPLY), completion(json_reply)])
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Cập nhật.", newer_than=memory)
    write_fact(deps, "ngu-som")
    write_fact(deps, "tra-den")

    await consolidate_memory(deps, hub)
    created = texts.FACT_REVIEW_CREATED.format(count=2)
    assert hub.recent(5)[0].summary == f"{texts.CONSOLIDATE_UNCHANGED} {created}"


async def test_a_review_with_nothing_to_do_adds_nothing_to_the_summary(deps_factory, hub):
    deps = deps_factory(script=[completion(REWRITE_REPLY), completion("[]")])
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Cập nhật.", newer_than=memory)
    write_fact(deps, "ngu-som")

    await consolidate_memory(deps, hub)
    assert hub.recent(5)[0].summary == texts.CONSOLIDATE_UNCHANGED


async def test_a_broken_reply_is_named_in_the_summary(deps_factory, hub):
    deps = deps_factory(script=[completion(REWRITE_REPLY), completion("JSON hỏng")])
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Cập nhật.", newer_than=memory)
    write_fact(deps, "ngu-som")

    await consolidate_memory(deps, hub)
    broken = texts.FACT_REVIEW_BROKEN_JSON
    assert hub.recent(5)[0].summary == f"{texts.CONSOLIDATE_UNCHANGED} {broken}"


async def test_a_review_that_raises_still_finishes_the_run_and_says_so(
    deps_factory, hub, monkeypatch
):
    async def boom(*_args, **_kwargs):
        raise RuntimeError("gãy")

    monkeypatch.setattr(fact_review, "review_user_facts", boom)
    deps = deps_factory(script=[completion(REWRITE_REPLY)])
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Cập nhật.", newer_than=memory)
    write_fact(deps, "ngu-som")

    await consolidate_memory(deps, hub)
    run = hub.recent(5)[0]
    assert run.status == "done"
    assert run.summary == f"{texts.CONSOLIDATE_UNCHANGED} {texts.FACT_REVIEW_FAILED}"


async def test_the_review_reads_the_same_budgeted_notes_as_the_rewrite(deps_factory, hub):
    deps = deps_factory(script=[completion(REWRITE_REPLY), completion("[]")])
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-18", "z" * (consolidate.MAX_INPUT_CHARS + 10), newer_than=memory)
    write_note(deps, "2026-09-19", "Ghi chép nhỏ.", newer_than=memory)
    write_fact(deps, "ngu-som")

    await consolidate_memory(deps, hub)
    for index in (0, 1):
        sent = prompt_sent(deps, index)
        assert "Ghi chép nhỏ." in sent
        assert "z" * 1000 not in sent  # the day that did not fit is left out of both calls


class _LaterToday(date):
    @classmethod
    def today(cls) -> date:
        return cls(2027, 1, 15)


async def test_the_review_judges_staleness_by_the_same_today_as_the_rewrite(
    deps_factory, hub, monkeypatch
):
    monkeypatch.setattr(consolidate, "date", _LaterToday)
    deps = deps_factory(script=[completion(REWRITE_REPLY), completion("[]")])
    memory = write_memory(deps, "- Sếp thích trà.")
    write_note(deps, "2026-09-19", "Cập nhật.", newer_than=memory)
    write_fact(deps, "cu-roi", now=datetime(2026, 9, 20, 8))  # stale by 2027-01-15 only
    write_fact(deps, "con-moi", now=datetime(2026, 12, 20, 8))

    await consolidate_memory(deps, hub)
    sent = prompt_sent(deps, 1)
    assert sent.index("- cu-roi (") < sent.index("- con-moi (")
