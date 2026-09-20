"""Whether a memory write lands or waits depends on who asked for it."""

from __future__ import annotations

import pytest

from my_agent_crew.agent.turn_context import CHAT, JOB, TELEGRAM, set_turn_source
from my_agent_crew.memory import user_store
from my_agent_crew.store import Store
from my_agent_crew.store.memory_proposals import PENDING, USER_FACT, USER_FORGET
from my_agent_crew.tools.memory_user import build_user_memory_tools
from my_agent_crew.tools.registry import ToolError


@pytest.fixture
def tools(tmp_path, store: Store):
    return {t.name: t for t in build_user_memory_tools(tmp_path / "owner", store, "coach")}


@pytest.fixture(autouse=True)
def _default_source():
    set_turn_source(CHAT)
    yield
    set_turn_source(CHAT)


ARGS = {
    "name": "ngu-som",
    "description": "Ngủ trước 23h",
    "type": "preference",
    "body": "Người dùng muốn ngủ trước 23h mỗi ngày.",
}


async def test_a_chat_turn_writes_the_fact_and_indexes_it(tmp_path, tools, store: Store):
    user_dir = tmp_path / "owner"
    await tools["user_memory_save"].run(dict(ARGS))

    facts = user_store.list_facts(user_dir)
    assert [f.name for f in facts] == ["ngu-som"]
    assert facts[0].body == ARGS["body"]
    assert facts[0].written_by == "coach" and facts[0].source == CHAT
    assert "ngu-som.md" in user_store.read_index(user_dir)
    assert store.proposals.list() == []


async def test_telegram_counts_as_the_person_being_present(tmp_path, tools, store: Store):
    set_turn_source(TELEGRAM)
    await tools["user_memory_save"].run(dict(ARGS))

    assert user_store.list_facts(tmp_path / "owner") != []
    assert store.proposals.list() == []


async def test_a_job_proposes_instead_of_writing(tmp_path, tools, store: Store):
    set_turn_source("job:coach/brief")
    out = await tools["user_memory_save"].run(dict(ARGS))

    assert user_store.list_facts(tmp_path / "owner") == []
    (proposal,) = store.proposals.list()
    assert proposal.kind == USER_FACT and proposal.status == PENDING
    assert proposal.name == "ngu-som" and proposal.body == ARGS["body"]
    assert proposal.agent_id == "coach" and proposal.source == JOB
    assert "ngu-som" in out


async def test_forgetting_removes_the_fact_when_the_person_is_there(tmp_path, tools):
    user_dir = tmp_path / "owner"
    await tools["user_memory_save"].run(dict(ARGS))
    await tools["user_memory_forget"].run({"name": "ngu-som"})

    assert user_store.list_facts(user_dir) == []


async def test_forgetting_an_unknown_fact_says_so_rather_than_failing(tools):
    out = await tools["user_memory_forget"].run({"name": "khong-co"})
    assert "khong-co" in out


async def test_a_job_proposes_the_forget_too(tmp_path, tools, store: Store):
    await tools["user_memory_save"].run(dict(ARGS))
    set_turn_source(JOB)
    await tools["user_memory_forget"].run({"name": "ngu-som"})

    assert user_store.list_facts(tmp_path / "owner") != []
    (proposal,) = store.proposals.list()
    assert proposal.kind == USER_FORGET and proposal.name == "ngu-som"


@pytest.mark.parametrize("name", ["Ngu Som", "ngu_som", "", "a" * 61])
async def test_a_name_that_is_not_a_slug_is_refused(tools, name):
    with pytest.raises(ToolError):
        await tools["user_memory_save"].run(dict(ARGS, name=name))


async def test_an_unknown_fact_type_is_refused(tools):
    with pytest.raises(ToolError):
        await tools["user_memory_save"].run(dict(ARGS, type="gossip"))


async def test_saving_the_same_name_twice_updates_rather_than_duplicates(tmp_path, tools):
    await tools["user_memory_save"].run(dict(ARGS))
    await tools["user_memory_save"].run(dict(ARGS, body="Đổi ý: trước 22h."))

    (fact,) = user_store.list_facts(tmp_path / "owner")
    assert fact.body == "Đổi ý: trước 22h."
    assert user_store.read_index(tmp_path / "owner").count("ngu-som.md") == 1
