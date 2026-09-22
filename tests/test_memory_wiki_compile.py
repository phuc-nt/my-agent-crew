"""The scheduled compile: what it proposes, what it writes, and what it refuses."""

from __future__ import annotations

import json

import pytest

from my_agent_crew.activity import ActivityHub
from my_agent_crew.llm.fake import completion
from my_agent_crew.memory import agent_store, wiki_store
from my_agent_crew.memory.proposals_apply import apply_proposal
from my_agent_crew.memory.wiki_apply import WIKI_COMPILE
from my_agent_crew.memory.wiki_compile import JOB_SOURCE, compile_wiki, existing_titles
from my_agent_crew.memory.wiki_reports import STALE_NAME, reports_dir
from my_agent_crew.memory.wiki_store import Page
from my_agent_crew.store.memory_proposals import APPROVED, PENDING
from my_agent_crew.store.runs import DONE
from my_agent_crew.tools import wiki_texts as texts

BODY = "Hạn nộp hồ sơ là thứ tư, đã dời một lần từ thứ hai tuần trước."
REPLY = json.dumps(
    [{"title": "Hạn Eco", "kind": "entities", "body": BODY, "sources": ["note:2026-09-19"]}],
    ensure_ascii=False,
)


@pytest.fixture
def hub(store) -> ActivityHub:
    return ActivityHub(store)


def write_note(deps, day="2026-09-19", text="Hạn Eco dời sang thứ tư."):
    agent_store.write_note(deps.agent.memory_dir, day, text)


async def test_an_agent_with_no_notes_never_asks_the_model(deps_factory, hub):
    """A compile on an empty history would invent pages out of nothing."""
    deps = deps_factory(script=[completion(REPLY)])
    assert await compile_wiki(deps, hub) is None
    assert deps.store.proposals.list() == []
    assert hub.recent(5)[0].summary == texts.WIKI_COMPILE_NOTHING_NEW


async def test_pages_wait_for_approval_and_the_vault_stays_empty(deps_factory, hub):
    deps = deps_factory(script=[completion(REPLY)])
    write_note(deps)

    proposal = await compile_wiki(deps, hub)
    assert proposal is not None
    assert proposal.kind == WIKI_COMPILE and proposal.status == PENDING
    assert proposal.source == JOB_SOURCE
    assert "Hạn Eco" in proposal.description
    # Nothing is written until someone decides, so a bad compile costs nothing.
    assert wiki_store.list_pages(deps.agent.memory_dir) == []

    run = hub.recent(5)[0]
    assert run.status == DONE and run.conversation_id is None


async def test_approving_writes_the_pages(deps_factory, hub):
    deps = deps_factory(script=[completion(REPLY)])
    write_note(deps)
    proposal = await compile_wiki(deps, hub)

    decided = apply_proposal(
        deps.store,
        proposal.id,
        approve=True,
        user_dir=deps.settings.user_dir,
        memory_dirs={deps.agent.id: deps.agent.memory_dir},
    )
    assert decided.status == APPROVED
    page = wiki_store.find_page(deps.agent.memory_dir, "han-eco")
    assert page.title == "Hạn Eco" and page.sources == ["note:2026-09-19"]


async def test_rejecting_writes_nothing(deps_factory, hub):
    deps = deps_factory(script=[completion(REPLY)])
    write_note(deps)
    proposal = await compile_wiki(deps, hub)

    apply_proposal(
        deps.store,
        proposal.id,
        approve=False,
        user_dir=deps.settings.user_dir,
        memory_dirs={deps.agent.id: deps.agent.memory_dir},
    )
    assert wiki_store.list_pages(deps.agent.memory_dir) == []


async def test_an_autonomous_agent_writes_straight_away(deps_factory, hub):
    deps = deps_factory(script=[completion(REPLY)], autonomous_default=True)
    write_note(deps)

    proposal = await compile_wiki(deps, hub)
    assert proposal.status == APPROVED
    assert wiki_store.find_page(deps.agent.memory_dir, "han-eco") is not None
    assert "1" in hub.recent(5)[0].summary


async def test_approving_refreshes_the_dashboards(deps_factory, hub):
    """A report that lags the vault it reports on is worse than no report."""
    deps = deps_factory(script=[completion(REPLY)], autonomous_default=True)
    write_note(deps)
    await compile_wiki(deps, hub)
    text = (reports_dir(deps.agent.memory_dir) / STALE_NAME).read_text(encoding="utf-8")
    assert "han-eco" not in text  # a fresh, sourced page has nothing to report


async def test_a_page_the_model_gave_no_sources_is_never_proposed(deps_factory, hub):
    """The rule that makes the vault worth reading is enforced before the proposal,
    not left to whoever approves it."""
    deps = deps_factory(
        script=[completion(json.dumps([{"title": "Hạn Eco", "body": BODY, "sources": []}]))]
    )
    write_note(deps)
    assert await compile_wiki(deps, hub) is None
    assert deps.store.proposals.list() == []


async def test_a_reply_with_no_usable_pages_finishes_quietly(deps_factory, hub):
    deps = deps_factory(script=[completion("Xin lỗi, tôi không tìm được gì.")])
    write_note(deps)
    assert await compile_wiki(deps, hub) is None
    assert hub.recent(5)[0].status == DONE


async def test_what_the_pages_said_before_is_kept_for_a_step_back(deps_factory, hub):
    deps = deps_factory(script=[completion(REPLY)])
    write_note(deps)
    wiki_store.write_page(
        deps.agent.memory_dir,
        Page(slug="han-eco", kind="entities", title="Hạn Eco", body="bản cũ", sources=["note:x"]),
    )

    proposal = await compile_wiki(deps, hub)
    [before] = json.loads(proposal.previous_body)
    assert before["body"] == "bản cũ"


async def test_the_existing_vault_is_shown_to_the_model_by_name_only(deps_factory):
    """Sending the bodies back would spend the whole budget re-reading what it wrote."""
    deps = deps_factory(script=[completion(REPLY)])
    wiki_store.write_page(
        deps.agent.memory_dir,
        Page(slug="han-eco", kind="entities", title="Hạn Eco", body="BÍ MẬT", sources=["note:x"]),
    )
    listed = existing_titles(deps.agent.memory_dir)
    assert "Hạn Eco" in listed and "BÍ MẬT" not in listed


async def test_an_empty_vault_says_so_rather_than_sending_nothing(deps_factory):
    deps = deps_factory(script=[completion(REPLY)])
    assert existing_titles(deps.agent.memory_dir) == texts.WIKI_COMPILE_NO_PAGES


async def test_the_model_is_told_to_link_the_pages_to_each_other(deps_factory, hub):
    """A first compile on real notes produced 23 pages and not one link, because the
    instruction was one clause among six. Unlinked pages are just notes that moved house,
    so the ask is pinned here: both in the rules and in the shape of a body."""
    deps = deps_factory(script=[completion(REPLY)])
    write_note(deps)
    await compile_wiki(deps, hub)
    sent = deps.chain.providers["scripted"].requests[0].messages[0].content
    rules, shape = sent.split("Trả về DUY NHẤT", 1)
    assert "[[" in rules
    assert "[[" in shape.split("--- trang đã có ---")[0]
