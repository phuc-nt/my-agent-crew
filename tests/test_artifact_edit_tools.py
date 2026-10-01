"""Changing a canvas through the tools: an edit lands only where its `old` still stands and
quotes back what changed, a rewrite starts only from the newest version the conversation saw
whole, and a write over versions it never saw says who wrote them."""

import pytest

from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import (
    ARTIFACT_AUTHORS,
    ARTIFACT_EDIT_AMBIGUOUS,
    ARTIFACT_EDIT_NO_MATCH,
    ARTIFACT_KIND_CLOSED,
    ARTIFACT_NOT_FOUND,
    ARTIFACT_REWRITE_UNSEEN,
    ARTIFACT_VERSION_CONFLICT,
    LINES_CUT,
)
from my_agent_crew.tools.artifact_texts import (
    ARTIFACT_CONFLICT_DIFF,
    ARTIFACT_RENAMED,
    ARTIFACT_REWRITTEN,
    ARTIFACT_UNCHANGED,
)
from tests.canvas_helpers import (
    LongNote,
    agents_canvas,
    before_note,
    call,
    child_turn,
    lines_text,
    lock_is_free,
    persons_canvas,
    seen,
    tagged,
    turn,
)

PLAN = "# Kế hoạch\nchạy 5 km\nbơi\n"


@pytest.fixture(autouse=True)
def fresh_turn():
    set_turn_source(CHAT)
    set_turn_conversation("")
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


def _failed(message: str) -> str:
    return TOOL_FAILED.format(error=message)


async def _created(store: Store, content: str = PLAN, title: str = "Kế hoạch") -> str:
    args = {"title": title, "kind": "markdown", "content": content}
    art, version, _ = tagged(await call(store, "artifact_create", args))
    assert version == 1
    return art


async def _read_whole(store: Store, art: str) -> None:
    result = await call(store, "artifact_read", {"id": art})
    assert result.output.endswith("\nHết canvas."), result.output


async def test_an_edit_quotes_back_the_lines_it_changed_and_makes_its_version_seen(
    store: Store,
):
    conv = turn(store)
    art = await _created(store)
    result = await call(store, "artifact_edit", {"id": art, "old": "chạy 5 km", "new": "chạy 8 km"})
    diff = "```diff\n@@ dòng 2 @@\n- chạy 5 km\n+ chạy 8 km\n```"
    assert result.output == f"[artifact {art} v2]\nĐã thay 1 chỗ.\n{diff}"
    assert store.artifacts.head(art).content == "# Kế hoạch\nchạy 8 km\nbơi\n"
    assert seen(store, conv, art) == 2


async def test_an_edit_over_a_persons_save_names_it_and_leaves_it_unseen(store: Store):
    conv = turn(store)
    art = await _created(store)
    store.artifacts.write(art, "# Kế hoạch\nchạy 5 km\nbơi 1 km\n", USER, "")
    result = await call(store, "artifact_edit", {"id": art, "old": "chạy 5 km", "new": "chạy 8 km"})
    authors = ARTIFACT_AUTHORS.format(groups="v2 người")
    diff = "```diff\n@@ dòng 2 @@\n- chạy 5 km\n+ chạy 8 km\n```"
    assert result.output == f"[artifact {art} v3]\nĐã thay 1 chỗ.\n{authors}\n{diff}"
    assert store.artifacts.head(art).content == "# Kế hoạch\nchạy 8 km\nbơi 1 km\n"
    assert seen(store, conv, art) == 1


async def test_the_nearest_passage_to_a_missed_edit_is_looked_for_outside_the_lock(
    store: Store, monkeypatch
):
    free: list[bool] = []

    def nearest(text, old):
        free.append(lock_is_free(store))
        return None

    monkeypatch.setattr("my_agent_crew.tools.text_nearest.nearest_region", nearest)
    turn(store)
    art = await _created(store)
    result = await call(store, "artifact_edit", {"id": art, "old": "đạp xe", "new": "bơi"})
    assert result.output == _failed(ARTIFACT_EDIT_NO_MATCH)
    assert free == [True]
    assert store.artifacts.head(art).version == 1


async def test_an_edit_diff_fits_any_cap_and_leaves_a_hooks_note_to_be_cut_first(store: Store):
    """The diff leaves room for the registry's cut mark, so a note a hook adds after it is what
    gets shortened, never the diff."""
    conv = turn(store)
    art = await _created(store, lines_text(100))
    old, new = "x" * 29, "y" * 29
    for limit in range(600, 750, 3):
        turn(store, conv)  # each turn has its own write budget
        edit = {"id": art, "old": old, "new": new, "replace_all": True}
        result = await call(store, "artifact_edit", edit, limit=limit, hooks=LongNote())
        tag, edited, diff = before_note(result.output).split("\n", 2)
        assert edited == "Đã thay 100 chỗ."
        assert diff.startswith("```diff\n@@ dòng 1–100 @@\n") and diff.endswith("\n```")
        old, new = new, old


async def test_an_edit_that_changes_nothing_adds_no_version_yet_still_renames(store: Store):
    turn(store)
    art = await _created(store)
    same = {"id": art, "old": "bơi", "new": "bơi"}
    unchanged = f"[artifact {art} v1 unchanged]\n{ARTIFACT_UNCHANGED}"
    assert (await call(store, "artifact_edit", same)).output == unchanged
    line_end = {"id": art, "old": "chạy 5 km\n", "new": "chạy 5 km\r\n"}
    assert (await call(store, "artifact_edit", line_end)).output == unchanged
    titled = await call(store, "artifact_edit", {**same, "title": "Kế hoạch"})
    assert titled.output == unchanged
    renamed = await call(store, "artifact_edit", {**same, "title": "  Kế hoạch mới "})
    assert renamed.output == f"{unchanged}\n{ARTIFACT_RENAMED.format(title='Kế hoạch mới')}"
    assert store.artifacts.get(art).title == "Kế hoạch mới"
    assert store.artifacts.head(art).version == 1


async def test_a_rewrite_needs_the_canvas_read_whole_first(store: Store):
    """Listing it, reading its first page or skipping to its last never lets one through."""
    conv = turn(store)
    art = persons_canvas(store, lines_text(400), conv.id)
    rewrite = {"id": art, "content": "mới"}
    refused = _failed(ARTIFACT_REWRITE_UNSEEN.format(id=art))
    assert (await call(store, "artifact_list", {})).output.endswith(" — chưa đọc")
    assert (await call(store, "artifact_rewrite", rewrite)).output == refused
    first = await call(store, "artifact_read", {"id": art})
    assert first.ok and not first.output.endswith("Hết canvas.")
    assert (await call(store, "artifact_rewrite", rewrite)).output == refused
    last = await call(store, "artifact_read", {"id": art, "from_line": 400})
    assert last.output.endswith("Hết canvas.")
    assert (await call(store, "artifact_rewrite", rewrite)).output == refused
    assert store.artifacts.head(art).version == 1


async def test_a_rewrite_over_a_persons_save_is_refused_with_what_they_changed(store: Store):
    conv = turn(store)
    text = lines_text(100)
    art = await _created(store, text)
    store.artifacts.write(art, text.replace("dòng", "DÒNG"), USER, "")
    result = await call(store, "artifact_rewrite", {"id": art, "content": "mới"}, limit=2000)
    conflict = ARTIFACT_VERSION_CONFLICT.format(head=2)
    authors = ARTIFACT_AUTHORS.format(groups="v2 người")
    heading = ARTIFACT_CONFLICT_DIFF.format(seen=1, head=2)
    assert result.output.startswith(_failed(f"{conflict}\n{authors}\n{heading}\n```diff\n"))
    assert "\n@@ dòng 1–100 @@\n- dòng 00001 " in result.output
    assert "\n+ DÒNG 00001 " in result.output
    assert LINES_CUT.split("{")[0] in result.output
    assert len(result.output) <= 2000 and result.output.endswith("\n```")
    assert "đã cắt bớt" not in result.output
    assert (seen(store, conv, art), store.artifacts.head(art).version) == (1, 2)


async def test_a_conflict_fits_any_cap_and_leaves_a_hooks_note_to_be_cut_first(store: Store):
    turn(store)
    text = lines_text(100)
    art = await _created(store, text)
    store.artifacts.write(art, text.replace("dòng", "DÒNG"), USER, "")
    rewrite = {"id": art, "content": "mới"}
    conflict = _failed(ARTIFACT_VERSION_CONFLICT.format(head=2))
    for limit in range(700, 850, 3):
        result = await call(store, "artifact_rewrite", rewrite, limit=limit, hooks=LongNote())
        refusal = before_note(result.output)
        assert refusal.startswith(conflict) and refusal.endswith("\n```")
    assert store.artifacts.head(art).version == 2


async def test_a_rewrite_from_the_newest_version_read_whole_writes_it(store: Store):
    conv = turn(store)
    art = persons_canvas(store, PLAN, conv.id)
    await _read_whole(store, art)
    content = "# Kế hoạch mới\nđạp xe"
    args = {"id": art, "content": content, "title": "Tuần sau"}
    result = await call(store, "artifact_rewrite", args)
    done = ARTIFACT_REWRITTEN.format(size=len(content.encode()), lines=2)
    assert result.output == f"[artifact {art} v2]\n{done}"
    assert store.artifacts.head(art).content == content
    assert store.artifacts.get(art).title == "Tuần sau"
    assert seen(store, conv, art) == 2


async def test_a_rewrite_that_only_changes_line_endings_changes_nothing(store: Store):
    conv = turn(store)
    art = persons_canvas(store, PLAN, conv.id)
    await _read_whole(store, art)
    result = await call(
        store, "artifact_rewrite", {"id": art, "content": PLAN.replace("\n", "\r\n")}
    )
    assert tagged(result) == (art, 1, True)
    assert result.output.endswith(ARTIFACT_UNCHANGED)
    assert store.artifacts.head(art).version == 1


@pytest.mark.parametrize("tool", ["artifact_edit", "artifact_rewrite"])
async def test_a_delegated_child_shares_what_it_changes_with_the_root(store: Store, tool: str):
    """The chain's later children reach a canvas one child changed, as they reach one it made."""
    root = store.create()
    art = agents_canvas(store, "coach")
    child = child_turn(store, root)
    if tool == "artifact_edit":
        args = {"id": art, "old": "# Kế hoạch", "new": "# Kế hoạch tuần"}
    else:
        await _read_whole(store, art)
        args = {"id": art, "content": "# Kế hoạch tuần\n"}
    assert tagged(await call(store, tool, args))[1] == 2
    for conversation_id in (child.id, root.id):
        link = store.artifact_links.get(conversation_id, art)
        assert link is not None and link.shared
    child_turn(store, root)
    assert (await call(store, "artifact_read", {"id": art}, agent_id="researcher")).ok


async def test_a_kind_agents_do_not_write_is_refused_only_once_the_canvas_is_in_reach(
    store: Store,
):
    """Out of reach, the refusal is the one for a canvas that does not exist, so it never
    tells the kind of a canvas the agent cannot open."""
    conv = turn(store)
    linked = persons_canvas(store, "<p>chào</p>", conv.id, kind="html")
    hidden = persons_canvas(store, "<p>ẩn</p>", kind="html")
    await _read_whole(store, linked)
    closed = _failed(ARTIFACT_KIND_CLOSED.format(kinds="markdown, code"))
    edit = {"old": "chào", "new": "xin chào"}
    assert (await call(store, "artifact_edit", {"id": linked, **edit})).output == closed
    rewrite = {"id": linked, "content": "<p>mới</p>"}
    assert (await call(store, "artifact_rewrite", rewrite)).output == closed
    missing = _failed(ARTIFACT_NOT_FOUND.format(id=hidden))
    assert (await call(store, "artifact_edit", {"id": hidden, **edit})).output == missing
    assert store.artifacts.head(linked).version == 1


async def test_a_diff_quoting_backticks_gets_a_longer_fence(store: Store):
    turn(store)
    art = await _created(store, "# Mã\n```python\nprint(1)\n```\n")
    result = await call(store, "artifact_edit", {"id": art, "old": "```python", "new": "````py"})
    diff = "`````diff\n@@ dòng 2 @@\n- ```python\n+ ````py\n`````"
    assert result.output == f"[artifact {art} v2]\nĐã thay 1 chỗ.\n{diff}"


async def test_an_edit_matching_twice_is_refused_unless_every_match_is_replaced(store: Store):
    turn(store)
    art = await _created(store, "bơi\nchạy\nbơi")
    edit = {"id": art, "old": "bơi", "new": "đạp xe"}
    result = await call(store, "artifact_edit", edit)
    assert result.output == _failed(ARTIFACT_EDIT_AMBIGUOUS.format(count=2))
    assert store.artifacts.head(art).version == 1
    assert tagged(await call(store, "artifact_edit", {**edit, "replace_all": True}))[1] == 2
    assert store.artifacts.head(art).content == "đạp xe\nchạy\nđạp xe"
