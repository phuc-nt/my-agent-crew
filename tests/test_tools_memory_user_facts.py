"""What the fact tools say back as a write is reconciled, and what `user_memory_get` reads."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from my_agent_crew import texts_facts
from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.memory import fact_recall, user_store
from my_agent_crew.store import Store
from my_agent_crew.store.memory_proposals import USER_FACT
from my_agent_crew.tools.memory import build_memory_tools
from my_agent_crew.tools.memory_user import build_user_memory_tools
from my_agent_crew.tools.registry import ToolError

ARGS = {"name": "do-uong", "description": "Thích trà", "type": "preference", "body": "Trà xanh"}


@pytest.fixture
def user_dir(tmp_path):
    return tmp_path / "owner"


@pytest.fixture
def tools(user_dir, store: Store):
    return {t.name: t for t in build_user_memory_tools(user_dir, store, "coach")}


@pytest.fixture(autouse=True)
def _chat():
    set_turn_source(CHAT)
    set_turn_conversation("c1")
    yield
    set_turn_conversation("")


async def test_a_write_records_the_conversation_it_came_from(user_dir, tools):
    out = await tools["user_memory_save"].run(dict(ARGS))
    assert out == texts_facts.USER_MEMORY_CREATED.format(name="do-uong")
    fact = user_store.read_fact(user_dir, "do-uong")
    assert fact.sources == ("conv:c1",) and fact.stands_on == "said"


async def test_saying_it_again_confirms_and_a_new_claim_supersedes(user_dir, tools):
    await tools["user_memory_save"].run(dict(ARGS))
    again = await tools["user_memory_save"].run(dict(ARGS))
    changed = await tools["user_memory_save"].run({**ARGS, "body": "Cà phê"})

    assert again == texts_facts.USER_MEMORY_CONFIRMED.format(name="do-uong", version=1)
    assert changed == texts_facts.USER_MEMORY_SUPERSEDED.format(name="do-uong", version=2)


async def test_an_inference_against_the_persons_word_becomes_a_proposal(
    user_dir, tools, store: Store
):
    await tools["user_memory_save"].run(dict(ARGS))
    out = await tools["user_memory_save"].run({**ARGS, "body": "Cà phê", "basis": "inferred"})

    assert "Không ghi đè do-uong" in out and "người dùng nói" in out
    assert user_store.read_fact(user_dir, "do-uong").body == "Trà xanh"
    (proposal,) = store.proposals.list()
    assert proposal.kind == USER_FACT and proposal.body == "Cà phê"
    assert proposal.reasons == texts_facts.USER_MEMORY_DISPUTE_REASON.format(
        held="người dùng nói", version=1
    )


async def test_a_bad_basis_or_day_is_refused(tools):
    with pytest.raises(ToolError):
        await tools["user_memory_save"].run({**ARGS, "basis": "operator"})
    with pytest.raises(ToolError):
        await tools["user_memory_save"].run({**ARGS, "valid_from": "1/12"})


async def test_get_reads_the_fact_its_history_and_counts_the_read(user_dir, tools):
    await tools["user_memory_save"].run(dict(ARGS))
    await tools["user_memory_save"].run({**ARGS, "description": "Thích cà phê", "body": "Cà phê"})

    out = await tools["user_memory_get"].run({"name": "do-uong"})

    assert "phiên bản 2" in out and "Cà phê" in out and "người dùng nói" in out
    assert "nguồn: conv:c1" in out and "lịch sử:" in out and "v1 Thích trà" in out
    recall = fact_recall.read(user_store.facts_dir(user_dir))
    assert recall["do-uong"]["count"] == 1


async def test_get_as_of_a_day_before_a_change_reads_the_version_then(user_dir, tools):
    await tools["user_memory_save"].run(dict(ARGS))
    soon = (date.today() + timedelta(days=10)).isoformat()
    await tools["user_memory_save"].run({**ARGS, "body": "Cà phê", "valid_from": soon})

    now = await tools["user_memory_get"].run({"name": "do-uong"})
    later = await tools["user_memory_get"].run({"name": "do-uong", "as_of": soon})

    assert "Trà xanh" in now.split("lịch sử:")[0] and "bản hiện tại: phiên bản 2" in now
    assert "Cà phê" in later.split("lịch sử:")[0] and f"(đúng vào {soon})" in later


async def test_get_of_nothing_says_so(tools):
    assert "Không có ghi nhớ nào" in await tools["user_memory_get"].run({"name": "khong-co"})
    out = await tools["user_memory_get"].run({"name": "khong-co", "as_of": "2020-01-01"})
    assert out == texts_facts.USER_MEMORY_NOTHING_ON.format(name="khong-co", day="2020-01-01")


async def test_forget_retracts_and_keeps_the_history(user_dir, tools):
    await tools["user_memory_save"].run(dict(ARGS))
    out = await tools["user_memory_forget"].run({"name": "do-uong"})

    assert out == texts_facts.USER_MEMORY_RETRACTED.format(name="do-uong")
    assert user_store.read_fact(user_dir, "do-uong") is None
    history = await tools["user_memory_get"].run({"name": "do-uong", "as_of": "2000-01-01"})
    assert "Trà xanh" in history


async def test_a_search_that_finds_a_fact_counts_as_using_it(tmp_path, user_dir, tools):
    await tools["user_memory_save"].run(dict(ARGS))
    memory = {t.name: t for t in build_memory_tools(tmp_path / "mem", user_dir=user_dir)}

    await memory["memory_search"].run({"query": "trà"})

    assert fact_recall.read(user_store.facts_dir(user_dir))["do-uong"]["count"] == 1
