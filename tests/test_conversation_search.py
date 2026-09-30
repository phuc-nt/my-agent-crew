from pathlib import Path

import pytest

from my_agent_crew import texts
from my_agent_crew.agent.turn_context import set_turn_conversation
from my_agent_crew.agents.profile import AgentProfile, default_profile
from my_agent_crew.config import Route, Settings
from my_agent_crew.llm.types import Message
from my_agent_crew.server.tool_assembly import build_tools
from my_agent_crew.store import Store
from my_agent_crew.store.search import snippet
from my_agent_crew.tools.conversation_search import build_conversation_search_tool
from my_agent_crew.tools.registry import ToolRegistry


def user(text: str) -> Message:
    return Message(role="user", content=text)


def assistant(text: str) -> Message:
    return Message(role="assistant", content=text)


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


# --- store/search.py correctness -----------------------------------------------------


def test_doc_finds_dao_nang_typed_without_accents(store: Store) -> None:
    conv = store.create()
    store.append(conv.id, user("Tôi muốn đọc sách"))
    store.append(conv.id, assistant("Đà Nẵng đẹp lắm"))

    assert [h.snippet for h in store.search.find("doc")] == ["Tôi muốn đọc sách"]
    assert [h.snippet for h in store.search.find("da nang")] == ["Đà Nẵng đẹp lắm"]
    assert [h.snippet for h in store.search.find("DA NANG")] == ["Đà Nẵng đẹp lắm"]


def test_japanese_dakuten_is_kept_not_folded_like_a_vietnamese_accent(store: Store) -> None:
    conv = store.create()
    store.append(conv.id, user("ぶどうを食べた"))
    store.append(conv.id, user("ふとんに入った"))

    assert [h.snippet for h in store.search.find("ぶ")] == ["ぶどうを食べた"]
    assert [h.snippet for h in store.search.find("ふ")] == ["ふとんに入った"]
    # ふひん is a different word from ふびん; stripping the dakuten would wrongly equate them.
    assert store.search.find("ふひん") == []


def test_nfd_form_is_found_and_the_snippet_keeps_the_original_characters(store: Store) -> None:
    conv = store.create()
    decomposed = "Nguyẽn học bài"  # "Nguyễn học bài", NFD
    store.append(conv.id, user(decomposed))

    hits = store.search.find("nguyen")

    assert len(hits) == 1
    assert hits[0].snippet == decomposed


def test_snippet_marks_only_the_ends_it_actually_cut() -> None:
    # Terms arrive already normalized (lowercase, đ folded to d), as `terms_of` produces.
    long_text = "mở đầu " + "x" * 200 + " đọc ở giữa " + "y" * 200 + " kết thúc"
    cut = snippet(long_text, ["doc"], width=40)
    assert cut.startswith("…")
    assert cut.endswith("…")

    short_text = "một câu ngắn có đọc ở trong"
    whole = snippet(short_text, ["doc"], width=160)
    assert whole == short_text
    assert "…" not in whole


def test_snippet_falls_back_to_the_start_when_folding_changes_the_length() -> None:
    # NFD: "s", "a", combining acute, "n", "g" — 5 code points. Folding runs it through
    # NFC, which recomposes "á" into one code point, so the folded text is shorter than
    # the original and an offset found in one no longer lands on the same character in
    # the other.
    mismatched = "sáng"
    assert snippet(mismatched, ["sang"], width=1) == mismatched[0] + "…"
    # A term far from the start tells the fallback apart from trusting the drifted offset,
    # which would centre the cut on the wrong characters instead of starting at 0.
    drifted = "sa\u0301ng " + "x" * 10 + " doc"
    assert snippet(drifted, ["doc"], width=3) == drifted[:3] + "…"


@pytest.mark.parametrize("query", ['"*()', "()", "*", "", 'a"b', "x*y", "AND", "NEAR("])
def test_special_fts5_characters_never_crash_the_query(store: Store, query: str) -> None:
    conv = store.create()
    store.append(conv.id, user("một câu bình thường"))

    assert store.search.find(query) == []


def test_duplicate_content_in_several_conversations_of_one_agent_collapses_to_the_newest(
    store: Store,
) -> None:
    convs = [store.create(agent_id="default") for _ in range(3)]
    for conv in convs:
        store.append(conv.id, user("câu lặp lại giống hệt nhau"))

    hits = store.search.find("lặp lại giống hệt")

    assert len(hits) == 1
    assert hits[0].conversation_id == convs[-1].id


def test_duplicate_content_across_two_agents_keeps_both(store: Store) -> None:
    conv_a = store.create(agent_id="default")
    conv_b = store.create(agent_id="coach")
    store.append(conv_a.id, user("câu chung của hai agent"))
    store.append(conv_b.id, user("câu chung của hai agent"))

    hits = store.search.find("chung của hai agent")

    assert {h.agent_id for h in hits} == {"default", "coach"}


def test_one_conversation_never_contributes_more_than_three_hits(store: Store) -> None:
    conv = store.create()
    for i in range(5):
        store.append(conv.id, user(f"chủ đề trần kết quả {i}"))

    hits = store.search.find("chủ đề trần kết quả")

    assert len(hits) == 3


def test_limit_caps_the_total_number_of_hits(store: Store) -> None:
    for i in range(5):
        conv = store.create()
        store.append(conv.id, user(f"giới hạn tổng số {i}"))

    assert len(store.search.find("giới hạn tổng số", limit=2)) == 2


def test_since_filters_out_messages_before_that_date(store: Store) -> None:
    old_conv = store.create()
    old_msg = store.append(old_conv.id, user("tin cũ về dự án"))
    store._conn.execute(
        "UPDATE messages SET created_at = '2020-01-01T00:00:00+00:00' WHERE id = ?",
        (old_msg.id,),
    )
    store._conn.commit()
    new_conv = store.create()
    store.append(new_conv.id, user("tin mới về dự án"))

    hits = store.search.find("dự án", since="2025-01-01")

    assert [h.conversation_id for h in hits] == [new_conv.id]


def test_agent_ids_filters_to_only_the_named_agents(store: Store) -> None:
    conv_a = store.create(agent_id="default")
    conv_b = store.create(agent_id="coach")
    store.append(conv_a.id, user("nội dung agent mặc định"))
    store.append(conv_b.id, user("nội dung agent coach"))

    hits = store.search.find("nội dung agent", agent_ids=["coach"])

    assert [h.agent_id for h in hits] == ["coach"]


def test_exclude_conversation_removes_that_conversation_from_the_results(store: Store) -> None:
    running = store.create()
    other = store.create()
    store.append(running.id, user("chủ đề đang chạy"))
    store.append(other.id, user("chủ đề khác hội thoại"))

    hits = store.search.find("chủ đề", exclude_conversation=running.id)

    assert [h.conversation_id for h in hits] == [other.id]


# --- tools/conversation_search.py: scope and errors -----------------------------------


@pytest.fixture
def populated() -> Store:
    store = Store(":memory:")
    default_conv = store.create(agent_id="default")
    coach_conv = store.create(agent_id="coach")
    store.append(default_conv.id, user("master tìm được của mình"))
    store.append(coach_conv.id, user("coach tìm được của mình"))
    return store


async def test_master_without_agent_sees_every_agent_and_labels_them(populated: Store) -> None:
    tool = build_conversation_search_tool(populated, "default", is_master=True)
    reg = ToolRegistry([tool])

    result = await reg.execute("conversation_search", {"query": "tìm được của mình"})

    assert "[coach]" in result.output
    assert "master tìm được của mình" in result.output
    assert "coach tìm được của mình" in result.output


async def test_master_with_agent_sees_only_that_agent(populated: Store) -> None:
    tool = build_conversation_search_tool(populated, "default", is_master=True)
    reg = ToolRegistry([tool])

    result = await reg.execute("conversation_search", {"query": "tìm được", "agent": "coach"})

    assert "coach tìm được của mình" in result.output
    assert "master tìm được của mình" not in result.output


async def test_a_non_master_agent_only_sees_its_own_conversations_even_asking_for_another(
    populated: Store,
) -> None:
    tool = build_conversation_search_tool(populated, "coach", is_master=False)
    # The schema for a non-master agent has no "agent" property at all: a model cannot
    # even try to point it at another agent's conversations through this parameter.
    assert "agent" not in tool.parameters["properties"]
    reg = ToolRegistry([tool])

    result = await reg.execute(
        "conversation_search", {"query": "tìm được của mình", "agent": "default"}
    )

    assert "coach tìm được của mình" in result.output
    assert "master tìm được của mình" not in result.output


async def test_the_running_conversation_is_excluded_from_its_own_search(populated: Store) -> None:
    conv = populated.create(agent_id="default")
    populated.append(conv.id, user("chủ đề của lượt đang chạy"))
    set_turn_conversation(conv.id)
    try:
        tool = build_conversation_search_tool(populated, "default", is_master=True)
        reg = ToolRegistry([tool])

        result = await reg.execute("conversation_search", {"query": "chủ đề của lượt"})

        assert result.output == texts.CONVERSATION_SEARCH_EMPTY
    finally:
        set_turn_conversation("")


# "20260930" parses with `date.fromisoformat` yet compares below every stored
# "2026-09-30T…" timestamp, so only the explicit pattern keeps it from silently
# filtering out everything.
@pytest.mark.parametrize("since", ["30/09/2026", "20260930"])
async def test_a_badly_formatted_since_is_a_tool_error(populated: Store, since: str) -> None:
    tool = build_conversation_search_tool(populated, "default", is_master=True)
    reg = ToolRegistry([tool])

    result = await reg.execute("conversation_search", {"query": "tìm được", "since": since})

    assert result.ok is False
    assert texts.CONVERSATION_SEARCH_BAD_SINCE in result.output


async def test_a_query_with_nothing_to_search_for_is_a_tool_error(populated: Store) -> None:
    tool = build_conversation_search_tool(populated, "default", is_master=True)
    reg = ToolRegistry([tool])

    result = await reg.execute("conversation_search", {"query": "   "})

    assert result.ok is False
    assert texts.CONVERSATION_SEARCH_NO_TERMS in result.output


async def test_a_query_of_only_special_characters_still_runs_and_finds_nothing(
    populated: Store,
) -> None:
    """`terms_of` folds a run of punctuation into a literal term rather than dropping it,
    so this is not a `ToolError`; the query simply matches nothing, like any other miss."""
    tool = build_conversation_search_tool(populated, "default", is_master=True)
    reg = ToolRegistry([tool])

    result = await reg.execute("conversation_search", {"query": "***"})

    assert result.ok is True
    assert result.output == texts.CONVERSATION_SEARCH_EMPTY


async def test_no_hits_says_so_plainly(populated: Store) -> None:
    tool = build_conversation_search_tool(populated, "default", is_master=True)
    reg = ToolRegistry([tool])

    result = await reg.execute("conversation_search", {"query": "không có chữ nào khớp cả"})

    assert result.output == texts.CONVERSATION_SEARCH_EMPTY


# --- build_tools wiring: allow-lists --------------------------------------------------


def profile_for(
    settings: Settings, *, agent_id: str = "default", tools: tuple = ()
) -> AgentProfile:
    from dataclasses import replace

    base = default_profile(settings)
    if agent_id == "default":
        return replace(base, tools=tools)
    return replace(base, id=agent_id, tools=tools)


async def test_build_tools_includes_conversation_search_without_an_allow_list(
    tmp_path: Path,
) -> None:
    import httpx

    settings = Settings(home=tmp_path / "home", routes=(Route("fake", "echo"),))
    store = Store(":memory:")
    profile = profile_for(settings)

    registry = build_tools(profile, httpx.AsyncClient(), store, [])

    assert registry.get("conversation_search") is not None


async def test_build_tools_hides_conversation_search_when_the_allow_list_omits_it(
    tmp_path: Path,
) -> None:
    import httpx

    settings = Settings(home=tmp_path / "home", routes=(Route("fake", "echo"),))
    store = Store(":memory:")
    profile = profile_for(settings, tools=("shell_run",))

    registry = build_tools(profile, httpx.AsyncClient(), store, [])

    assert registry.get("conversation_search") is None
