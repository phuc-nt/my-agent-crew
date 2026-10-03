"""The canvas tools as the loop calls them: what creating and listing a canvas returns, which
channel may write, which canvases each agent reaches, how many versions a turn may write, and
what every refusal of the store tells the agent instead of a bare failure."""

import pytest

from my_agent_crew.agent.turn_context import (
    API,
    CHAT,
    TELEGRAM,
    set_turn_conversation,
    set_turn_source,
)
from my_agent_crew.artifacts.kinds import cap_bytes
from my_agent_crew.artifacts.tag import TAG_RE
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import (
    ARTIFACT_ARG_TEXT,
    ARTIFACT_BAD_LANGUAGE,
    ARTIFACT_BAD_TITLE,
    ARTIFACT_CHANNEL_CLOSED,
    ARTIFACT_CREATE_BUDGET,
    ARTIFACT_KIND_CLOSED,
    ARTIFACT_NO_CONVERSATION,
    ARTIFACT_NOT_FOUND,
    ARTIFACT_STORAGE_FULL,
    ARTIFACT_TOO_LARGE,
    ARTIFACT_WRITE_BUDGET,
)
from my_agent_crew.tools.artifact import build_artifact_tools
from my_agent_crew.tools.artifact_scope import CANVAS_WRITES_PER_TURN
from my_agent_crew.tools.artifact_texts import (
    ADD_BY_EDIT,
    ARTIFACT_CREATED,
    ARTIFACT_LIST_EMPTY,
    ARTIFACT_LIST_NO_MATCH,
    KEPT_GOES_TO_CANVAS,
    PAGE_RULES,
    PARAM_KIND,
)
from tests.canvas_helpers import (
    agents_canvas,
    call,
    child_turn,
    persons_canvas,
    seen,
    tagged,
    turn,
)

PLAN = "# Kế hoạch tuần\n\n- Thứ hai: chạy 5 km\n- Thứ tư: bơi"
WRITABLE = "markdown, code, html, svg, mermaid"
TOOLS = ("artifact_create", "artifact_list", "artifact_read", "artifact_edit", "artifact_rewrite")


@pytest.fixture(autouse=True)
def fresh_turn():
    set_turn_source(CHAT)
    set_turn_conversation("")
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


def _failed(message: str) -> str:
    return TOOL_FAILED.format(error=message)


def _create_args(title: str = "Kế hoạch tuần", content: str = PLAN, **extra: str) -> dict:
    return {"title": title, "kind": "markdown", "content": content, **extra}


def test_an_agent_gets_the_five_canvas_tools_none_asking_for_approval(store: Store):
    """A canvas keeps every version, so nothing an agent writes there is lost to the person."""
    tools = build_artifact_tools(store, "coach", False, 8000)
    assert tuple(tool.name for tool in tools) == TOOLS
    assert not any(tool.requires_approval or tool.parallel for tool in tools)
    kind = tools[0].parameters["properties"]["kind"]
    assert kind["enum"] == ["markdown", "code", "html", "svg", "mermaid"]
    assert kind["description"] == PARAM_KIND
    assert all(name in PARAM_KIND for name in kind["enum"])


def test_the_descriptions_send_a_kept_document_to_a_canvas_and_say_how_to_add_to_one(
    store: Store,
):
    """A model asked for five lines the person would keep editing wrote them in the chat, as
    the short answer the description sent there; what decides is whether the text is kept,
    not how long it is. And an edit replaces text, so adding a line needs one to anchor on."""
    tools = {t.name: t.description for t in build_artifact_tools(store, "coach", False, 8000)}
    assert KEPT_GOES_TO_CANVAS in tools["artifact_create"]
    assert "Câu trả lời ngắn" not in tools["artifact_create"]
    assert ADD_BY_EDIT in tools["artifact_edit"]


def test_the_create_description_tells_a_page_what_its_sandbox_will_not_let_it_do(store: Store):
    """A page runs with no network of its own, no storage and no windows. A model not told
    writes the page it knows, which then fails without a word, so the rules ride on the one
    description it reads before writing."""
    tools = {t.name: t.description for t in build_artifact_tools(store, "coach", False, 8000)}
    description = tools["artifact_create"]
    for rule in ("localStorage", "cdnjs.cloudflare.com", "cdn.jsdelivr.net", "unpkg.com"):
        assert rule in description, rule
    for rule in ("integrity", "alert", "fetch", "data:", "mermaid", "svg"):
        assert rule in description, rule
    assert PAGE_RULES in description
    for name in ("artifact_list", "artifact_read", "artifact_edit", "artifact_rewrite"):
        assert PAGE_RULES not in tools[name]


async def test_create_files_the_canvas_under_the_agent_and_returns_no_content(store: Store):
    conv = turn(store)
    result = await call(store, "artifact_create", _create_args())
    art, version, unchanged = tagged(result)
    size = len(PLAN.encode())
    done = ARTIFACT_CREATED.format(title="Kế hoạch tuần", kind="markdown", size=size, lines=4)
    assert result.output == f"[artifact {art} v1]\n{done}"
    assert (version, unchanged) == (1, False)
    summary = store.artifacts.get(art)
    assert (summary.agent_id, summary.kind, summary.head_version) == ("coach", "markdown", 1)
    head = store.artifacts.head(art)
    assert (head.author, head.conversation_id, head.content) == ("agent:coach", conv.id, PLAN)
    link = store.artifact_links.get(conv.id, art)
    assert link is not None and link.shared
    assert seen(store, conv, art) == 1


async def test_a_delegated_child_shares_what_it_creates_with_the_root(store: Store):
    """The root's later children reach it too, and the root has not seen it yet."""
    root = store.create()
    child = child_turn(store, root)
    art, _, _ = tagged(await call(store, "artifact_create", _create_args(), agent_id="researcher"))
    assert store.artifact_links.conversations_for(art) == [child.id, root.id]
    for conversation_id in (child.id, root.id):
        link = store.artifact_links.get(conversation_id, art)
        assert link is not None and link.shared
    assert (seen(store, child, art), seen(store, root, art)) == (1, 0)


@pytest.mark.parametrize(
    ("kind", "content"),
    [
        ("html", "<!doctype html>\n<h1>Kế hoạch</h1>\n"),
        ("svg", '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h8"/></svg>'),
        ("mermaid", "graph TD\n  A[Chạy] --> B[Bơi]\n"),
    ],
)
async def test_create_files_a_page_a_drawing_and_a_diagram_like_any_other_canvas(
    store: Store, kind: str, content: str
):
    conv = turn(store)
    result = await call(store, "artifact_create", _create_args(kind=kind, content=content))
    art, version, _ = tagged(result)
    size, lines = len(content.encode()), content.count("\n") + 1
    done = ARTIFACT_CREATED.format(title="Kế hoạch tuần", kind=kind, size=size, lines=lines)
    assert result.output == f"[artifact {art} v1]\n{done}"
    summary = store.artifacts.get(art)
    assert (summary.kind, summary.agent_id, summary.head_version) == (kind, "coach", 1)
    assert store.artifacts.head(art).content == content
    assert seen(store, conv, art) == 1


async def test_a_page_may_be_larger_than_a_document_but_has_its_own_cap(store: Store):
    turn(store)
    cap = cap_bytes("html")
    assert cap > cap_bytes("markdown")
    roomy = _create_args(kind="html", content="x" * (cap_bytes("markdown") + 1))
    assert tagged(await call(store, "artifact_create", roomy))[1] == 1
    over = await call(store, "artifact_create", _create_args(kind="html", content="x" * (cap + 1)))
    assert over.output == _failed(ARTIFACT_TOO_LARGE.format(kind="html", size=cap + 1, cap=cap))
    assert len(store.artifacts.list()) == 1


@pytest.mark.parametrize("kind", ["image", "pdf"])
async def test_create_refuses_a_kind_agents_do_not_write(store: Store, kind: str):
    turn(store)
    result = await call(store, "artifact_create", {**_create_args(), "kind": kind})
    assert result.output == _failed(ARTIFACT_KIND_CLOSED.format(kinds=WRITABLE))
    assert store.artifacts.list() == []


@pytest.mark.parametrize("source", [TELEGRAM, "job:coach/brief", API])
async def test_only_the_web_chat_writes_a_canvas_yet_any_channel_reads_one(store: Store, source):
    """A person is there on Telegram and the API too, but cannot see a canvas there."""
    art = agents_canvas(store, "coach", "# Kế hoạch\n- chạy\n")
    conv = turn(store, source=source)
    writes = [
        ("artifact_create", _create_args()),
        ("artifact_edit", {"id": art, "old": "chạy", "new": "bơi"}),
        ("artifact_rewrite", {"id": art, "content": "# Khác\n"}),
    ]
    for name, args in writes:
        assert (await call(store, name, args)).output == _failed(ARTIFACT_CHANNEL_CLOSED)
    assert store.artifact_links.links_for(conv.id) == []
    assert [summary.id for summary in store.artifacts.list()] == [art]
    assert store.artifacts.head(art).version == 1
    assert (await call(store, "artifact_read", {"id": art})).ok
    assert (await call(store, "artifact_list", {})).ok


@pytest.mark.parametrize(("root_source", "writes"), [(CHAT, True), (TELEGRAM, False), ("", False)])
async def test_a_delegated_child_writes_only_in_a_chain_begun_in_the_web_chat(
    store: Store, root_source: str, writes: bool
):
    child_turn(store, store.create(), root_source)
    result = await call(store, "artifact_create", _create_args(), agent_id="researcher")
    assert result.ok is writes
    if not writes:
        assert result.output == _failed(ARTIFACT_CHANNEL_CLOSED)


async def test_what_the_master_read_does_not_reach_its_delegated_child(store: Store):
    root = turn(store)
    art = persons_canvas(store, "# Ghi chú\n")
    assert (await call(store, "artifact_read", {"id": art}, agent_id="master", is_master=True)).ok
    assert store.artifact_links.get(root.id, art) is not None
    child_turn(store, root)
    result = await call(store, "artifact_read", {"id": art}, agent_id="researcher")
    assert result.output == _failed(ARTIFACT_NOT_FOUND.format(id=art))


async def test_a_read_in_one_child_never_widens_what_the_next_child_reaches(store: Store):
    root = store.create()
    art = agents_canvas(store, "coach")
    child_turn(store, root)
    assert (await call(store, "artifact_read", {"id": art}, agent_id="coach")).ok
    child_turn(store, root)
    result = await call(store, "artifact_read", {"id": art}, agent_id="researcher")
    assert result.output == _failed(ARTIFACT_NOT_FOUND.format(id=art))


@pytest.mark.parametrize("agent_id", ["coach", "researcher", "user"])
async def test_a_persons_canvas_is_reached_only_through_a_link(store: Store, agent_id: str):
    """Filed under agent "", which no agent id is, not even one named "user"."""
    art = persons_canvas(store, "# Ghi chú\n")
    conv = turn(store)
    result = await call(store, "artifact_read", {"id": art}, agent_id=agent_id)
    assert result.output == _failed(ARTIFACT_NOT_FOUND.format(id=art))
    listed = await call(store, "artifact_list", {}, agent_id=agent_id)
    assert listed.output == ARTIFACT_LIST_EMPTY
    assert (await call(store, "artifact_read", {"id": art}, agent_id="master", is_master=True)).ok
    store.artifact_links.link(conv.id, art)
    assert (await call(store, "artifact_read", {"id": art}, agent_id=agent_id)).ok


@pytest.mark.parametrize(("agent_id", "is_master"), [("coach", False), ("master", True)])
async def test_a_canvas_that_does_not_exist_reads_like_one_out_of_reach(
    store: Store, agent_id: str, is_master: bool
):
    turn(store)
    missing = "0123456789ab"
    for name, args in [
        ("artifact_read", {"id": missing}),
        ("artifact_edit", {"id": missing, "old": "a", "new": "b"}),
        ("artifact_rewrite", {"id": missing, "content": "b"}),
    ]:
        result = await call(store, name, args, agent_id=agent_id, is_master=is_master)
        assert result.output == _failed(ARTIFACT_NOT_FOUND.format(id=missing))


async def test_a_turn_writes_at_most_thirty_versions_of_one_canvas(store: Store):
    """A write that changed nothing is not counted, and another canvas has its own count."""
    turn(store)
    art, _, _ = tagged(await call(store, "artifact_create", _create_args("Đếm", "đếm 0")))
    for _ in range(5):
        assert tagged(await call(store, "artifact_edit", {"id": art, "old": "đếm", "new": "đếm"}))[
            2
        ]
    for n in range(CANVAS_WRITES_PER_TURN):
        edit = {"id": art, "old": f"đếm {n}", "new": f"đếm {n + 1}"}
        assert tagged(await call(store, "artifact_edit", edit))[1] == n + 2
    edit = {"id": art, "old": "đếm 30", "new": "đếm 31"}
    result = await call(store, "artifact_edit", edit)
    assert result.output == _failed(ARTIFACT_WRITE_BUDGET.format(limit=CANVAS_WRITES_PER_TURN))
    rewrite = await call(store, "artifact_rewrite", {"id": art, "content": "đếm lại"})
    assert rewrite.output == result.output
    assert store.artifacts.head(art).version == CANVAS_WRITES_PER_TURN + 1
    other = agents_canvas(store, "coach", "khác")
    edit = {"id": other, "old": "khác", "new": "khác nữa"}
    assert tagged(await call(store, "artifact_edit", edit))[1] == 2


async def test_a_turn_creates_at_most_thirty_canvases(store: Store):
    turn(store)
    for n in range(CANVAS_WRITES_PER_TURN):
        tagged(await call(store, "artifact_create", _create_args(f"Canvas {n}", "x")))
    result = await call(store, "artifact_create", _create_args("Một nữa", "x"))
    assert result.output == _failed(ARTIFACT_CREATE_BUDGET.format(limit=CANVAS_WRITES_PER_TURN))
    assert len(store.artifacts.list(limit=50)) == CANVAS_WRITES_PER_TURN
    set_turn_conversation(store.create().id)
    assert (await call(store, "artifact_create", _create_args("Lượt sau", "x"))).ok


async def test_list_flags_the_canvases_with_versions_this_conversation_has_not_seen(
    store: Store, canvas_clock
):
    """Newest first, at the owner's time, each flagged by what this conversation has seen."""
    old = agents_canvas(store, "coach")
    canvas_clock.tick(60)
    conv = turn(store)
    code = {"title": "Mã", "kind": "code", "content": "print(1)\n", "language": "python"}
    code_id, _, _ = tagged(await call(store, "artifact_create", code))
    canvas_clock.tick(60)
    week, _, _ = tagged(await call(store, "artifact_create", _create_args()))
    canvas_clock.tick(60)
    store.artifacts.write(week, PLAN + "\n- Chủ nhật: nghỉ", USER, conv.id)
    persons_canvas(store, "# Riêng\n")
    result = await call(store, "artifact_list", {})
    assert result.output == "\n".join(
        [
            f"- {week} «Kế hoạch tuần» (markdown, v2, sửa 1/10 10:03)"
            " — có bản mới (bạn thấy tới v1)",
            f"- {code_id} «Mã» (code python, v1, sửa 1/10 10:01)",
            f"- {old} «Kế hoạch» (markdown, v1, sửa 1/10 10:00) — chưa đọc",
        ]
    )
    assert TAG_RE.match(result.output) is None


async def test_list_matches_titles_and_the_master_lists_every_canvas(store: Store):
    agents_canvas(store, "coach")
    person = persons_canvas(store, "# Riêng\n")
    turn(store)
    assert (await call(store, "artifact_list", {}, agent_id="researcher")).output == (
        ARTIFACT_LIST_EMPTY
    )
    missed = await call(store, "artifact_list", {"query": " bơi "})
    assert missed.output == ARTIFACT_LIST_NO_MATCH.format(query="bơi")
    found = await call(store, "artifact_list", {"query": "KE HOACH"})
    assert found.output.count("\n") == 0 and "«Kế hoạch»" in found.output
    assert (await call(store, "artifact_list", {"query": "  "})).output == found.output
    everything = await call(store, "artifact_list", {}, agent_id="master", is_master=True)
    assert everything.output.count("\n") == 1 and person in everything.output


async def test_every_refusal_of_the_store_says_what_to_do_instead(store: Store, monkeypatch):
    turn(store)
    too_long = await call(store, "artifact_create", _create_args("T" * 201))
    assert too_long.output == _failed(ARTIFACT_BAD_TITLE.format(limit=200))
    language = await call(store, "artifact_create", _create_args(language="p" * 41))
    assert language.output == _failed(ARTIFACT_BAD_LANGUAGE.format(limit=40))
    cap = cap_bytes("markdown")
    large = await call(store, "artifact_create", _create_args(content="x" * (cap + 1)))
    assert large.output == _failed(
        ARTIFACT_TOO_LARGE.format(kind="markdown", size=cap + 1, cap=cap)
    )
    monkeypatch.setattr("my_agent_crew.store.artifacts.STORAGE_CAP", 100)
    full = await call(store, "artifact_create", _create_args(content="x" * 91))
    assert full.output == _failed(ARTIFACT_STORAGE_FULL.format(used=0, cap=90))
    assert store.artifacts.list() == []


@pytest.mark.parametrize(
    ("name", "args", "wrong"),
    [
        ("artifact_create", {"title": 5, "kind": "markdown", "content": "x"}, "title"),
        ("artifact_create", {"title": "T", "kind": "markdown", "content": ["x"]}, "content"),
        ("artifact_create", {"title": "T", "kind": "markdown"}, "content"),
        (
            "artifact_create",
            {"title": "T", "kind": "code", "content": "x", "language": 3},
            "language",
        ),
        ("artifact_read", {"id": 123}, "id"),
        ("artifact_edit", {"id": "0123456789ab", "old": "a", "new": None}, "new"),
        ("artifact_rewrite", {"id": "0123456789ab", "content": "a", "title": 7}, "title"),
        ("artifact_list", {"query": 1}, "query"),
    ],
)
async def test_an_argument_that_is_not_text_is_refused_before_anything_is_touched(
    store: Store, name: str, args: dict, wrong: str
):
    turn(store)
    result = await call(store, name, args)
    assert result.output == _failed(ARTIFACT_ARG_TEXT.format(name=wrong))
    assert store.artifacts.list() == []


@pytest.mark.parametrize("name", TOOLS)
async def test_every_tool_needs_the_conversation_of_a_turn(store: Store, name: str):
    art = agents_canvas(store, "coach")
    args = {"id": art, "title": "T", "kind": "markdown", "content": "x", "old": "K", "new": "k"}
    result = await call(store, name, args)
    assert result.output == _failed(ARTIFACT_NO_CONVERSATION)


async def test_each_write_opens_with_its_tag_and_a_read_or_a_list_never_does(store: Store):
    turn(store)
    art, version, _ = tagged(await call(store, "artifact_create", _create_args()))
    assert version == 1
    edit = {"id": art, "old": "Thứ", "new": "Ngày", "replace_all": "true"}
    edited = await call(store, "artifact_edit", edit)
    assert tagged(edited)[1:] == (2, False)
    assert edited.output.split("\n")[1] == "Đã thay 2 chỗ; canvas giờ có 65 byte, 4 dòng."
    rewrite = {"id": art, "content": "# Tuần sau\n"}
    assert tagged(await call(store, "artifact_rewrite", rewrite))[1:] == (3, False)
    same = {"id": art, "old": "Tuần sau", "new": "Tuần sau"}
    assert tagged(await call(store, "artifact_edit", same)) == (art, 3, True)
    for name, args in [("artifact_read", {"id": art}), ("artifact_list", {})]:
        result = await call(store, name, args)
        assert result.ok and TAG_RE.match(result.output) is None
