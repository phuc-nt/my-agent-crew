"""Reading a canvas a page at a time: each page fits the output cap whole even with a hook's
note after it, the pages of one version join back into its text, and only a read that went
from the first line to the last makes that version seen."""

import re

import pytest

from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import (
    ARTIFACT_AUTHORS,
    ARTIFACT_READ_BINARY,
    ARTIFACT_READ_PAST_END,
    ARTIFACT_REWRITE_UNSEEN,
    ARTIFACT_VERSION_GONE,
    LINE_CUT_TAIL,
)
from my_agent_crew.tools.artifact_texts import (
    ARTIFACT_READ_END,
    ARTIFACT_READ_HEADER,
    ARTIFACT_READ_MORE,
)
from tests.canvas_helpers import (
    LongNote,
    before_note,
    call,
    lines_text,
    persons_canvas,
    seen,
    turn,
)

AUTHORS_PREFIX = ARTIFACT_AUTHORS.split("{")[0]
MORE_RE = re.compile(r"Đọc tiếp: artifact_read id=[0-9a-f]{12} version=\d+ from_line=(\d+)")


@pytest.fixture(autouse=True)
def fresh_turn():
    set_turn_source(CHAT)
    set_turn_conversation("")
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


def _body(output: str) -> list[str]:
    """The canvas lines of a page: what lies between the header, with the authors line after
    it when there is one, and the footer."""
    lines = output.split("\n")[1:-1]
    return lines[1:] if lines and lines[0].startswith(AUTHORS_PREFIX) else lines


def _next_line(output: str) -> int | None:
    footer = output.rsplit("\n", 1)[-1]
    if footer == ARTIFACT_READ_END:
        return None
    match = MORE_RE.fullmatch(footer)
    assert match is not None, footer
    return int(match[1])


async def _read_on(store: Store, art: str, line: int | None, version: int = 1, **kwargs) -> list:
    """The pages from `line` on, following each footer until the last page."""
    outputs = []
    while line is not None:
        args = {"id": art, "version": version, "from_line": line}
        result = await call(store, "artifact_read", args, **kwargs)
        assert result.ok, result.output
        outputs.append(result.output)
        line = _next_line(result.output)
    return outputs


async def test_the_pages_of_a_canvas_fit_the_cap_and_join_back_into_its_text(store: Store):
    text = lines_text(400)
    conv = turn(store)
    art = persons_canvas(store, text, conv.id)
    first = await call(store, "artifact_read", {"id": art}, limit=2000)
    body = _body(first.output)
    shown = len(body)
    header = ARTIFACT_READ_HEADER.format(
        title="Ghi chú của người",
        id=art,
        version=1,
        kind="markdown",
        span=f"1–{shown}",
        total=400,
        behind="",
    )
    more = ARTIFACT_READ_MORE.format(id=art, version=1, line=shown + 1)
    authors = ARTIFACT_AUTHORS.format(groups="v1 người")
    assert first.output == "\n".join([header, authors, *body, more])
    assert body == text.split("\n")[:shown]
    pages = [first.output, *await _read_on(store, art, shown + 1, limit=2000)]
    assert all(len(page) <= 2000 and "đã cắt bớt" not in page for page in pages)
    assert all(len(_body(page)) >= 40 for page in pages[:-1])
    assert "\n".join(line for page in pages for line in _body(page)) == text
    assert seen(store, conv, art) == 1


async def test_a_hooks_note_is_cut_before_any_line_of_the_page_is(store: Store):
    text = lines_text(400)
    conv = turn(store)
    art = store.artifacts.create("T" * 200, "markdown", "", USER, "", text).id
    store.artifact_links.link(conv.id, art)
    result = await call(store, "artifact_read", {"id": art}, hooks=LongNote())
    assert len(result.output) <= 8000
    page = before_note(result.output)
    assert page.startswith(f"Canvas «{'T' * 200}» (id {art}, v1, markdown), dòng 1–")
    assert _next_line(page) == len(_body(page)) + 1
    assert _body(page) == text.split("\n")[: len(_body(page))]


async def test_a_line_too_long_for_a_page_is_cut_and_the_next_page_starts_after_it(
    store: Store,
):
    """What was cut off is never read, so the version is not seen and cannot be rewritten."""
    conv = turn(store)
    art = persons_canvas(store, "đầu\n" + "x" * 50000 + "\nsau", conv.id)
    first = await call(store, "artifact_read", {"id": art})
    assert (_body(first.output), _next_line(first.output)) == (["đầu"], 2)
    args = {"id": art, "version": 1, "from_line": 2}
    second = await call(store, "artifact_read", args, hooks=LongNote())
    assert len(second.output) <= 8000
    page = before_note(second.output)
    [cut] = _body(page)
    keep = cut.index("…")
    assert cut == "x" * keep + LINE_CUT_TAIL.format(n=50000 - keep)
    assert keep > 7000
    assert page.split("\n")[0].endswith("dòng 2 / 3")
    assert _next_line(page) == 3
    third = await call(store, "artifact_read", {"id": art, "version": 1, "from_line": 3})
    assert (_body(third.output), _next_line(third.output)) == (["sau"], None)
    assert seen(store, conv, art) == 0
    rewrite = await call(store, "artifact_rewrite", {"id": art, "content": "mới"})
    assert rewrite.output == TOOL_FAILED.format(error=ARTIFACT_REWRITE_UNSEEN.format(id=art))


async def test_only_a_read_from_the_first_line_to_the_last_makes_a_version_seen(store: Store):
    text = lines_text(400)
    conv = turn(store)
    art = persons_canvas(store, text, conv.id)
    [last] = await _read_on(store, art, 400, limit=2000)
    assert _body(last) == [text.split("\n")[-1]]
    assert seen(store, conv, art) == 0
    await _read_on(store, art, 1, limit=2000)
    assert seen(store, conv, art) == 1


async def test_a_save_between_two_pages_leaves_the_read_on_the_version_it_began(
    store: Store, canvas_clock
):
    """The read holds its version, so a person's save right after it is not folded away."""
    text = lines_text(400)
    conv = turn(store)
    art = persons_canvas(store, text, conv.id)
    first = await call(store, "artifact_read", {"id": art}, limit=2000)
    canvas_clock.tick(10)
    store.artifacts.write(art, text + "\nthêm", USER, "")
    assert store.artifacts.head(art).version == 2
    pages = await _read_on(store, art, _next_line(first.output), limit=2000)
    header = pages[0].split("\n")[0]
    assert f"(id {art}, v1, markdown)" in header
    assert header.endswith("/ 400; bản mới nhất là v2")
    assert seen(store, conv, art) == 1


async def test_a_version_a_save_folded_away_is_gone_and_the_newest_is_named(
    store: Store, canvas_clock
):
    """Listing holds no version, so the person's next save folds the first one away."""
    conv = turn(store)
    art = persons_canvas(store, "# Ghi chú\n", conv.id)
    assert (await call(store, "artifact_list", {})).ok
    canvas_clock.tick(10)
    store.artifacts.write(art, "# Ghi chú\nthêm\n", USER, "")
    result = await call(store, "artifact_read", {"id": art, "version": 1})
    gone = ARTIFACT_VERSION_GONE.format(version=1, head=2, id=art)
    assert result.output == TOOL_FAILED.format(error=gone)


async def test_every_page_names_who_wrote_the_versions_not_yet_seen(store: Store):
    text = lines_text(100)
    conv = turn(store)
    art = persons_canvas(store, text, conv.id)
    store.artifacts.write(art, text.replace("dòng 00002", "DÒNG 00002"), "agent:coach", "")
    store.artifacts.write(art, text.replace("dòng 00003", "DÒNG 00003"), USER, "")
    master = {"agent_id": "master", "is_master": True, "limit": 2000}
    pages = await _read_on(store, art, 1, version=3, **master)
    authors = ARTIFACT_AUTHORS.format(groups="v1 người, v2 agent:coach, v3 người")
    assert len(pages) > 1
    assert all(page.split("\n")[1] == authors for page in pages)
    assert seen(store, conv, art) == 3
    store.artifacts.write(art, text, USER, "")
    assert store.artifacts.head(art).version == 4
    [page, *_] = await _read_on(store, art, 1, version=4, **master)
    assert page.split("\n")[1] == ARTIFACT_AUTHORS.format(groups="v4 người")


async def test_a_page_of_a_set_number_of_lines_and_the_head_by_default(store: Store):
    conv = turn(store)
    art = persons_canvas(store, lines_text(20), conv.id)
    store.artifacts.write(art, lines_text(30), "agent:coach", "")
    capped = await call(store, "artifact_read", {"id": art, "version": 1, "lines": "5"})
    assert (_body(capped.output), _next_line(capped.output)) == (lines_text(5).split("\n"), 6)
    for version in ("abc", 0, -1, None):
        result = await call(store, "artifact_read", {"id": art, "version": version})
        assert f"(id {art}, v2, markdown), dòng 1–30 / 30" in result.output
    for line in (0, -3, "x"):
        result = await call(store, "artifact_read", {"id": art, "from_line": line})
        assert _body(result.output)[0] == lines_text(1)


async def test_read_refuses_a_line_past_the_end_and_a_kind_it_cannot_show(store: Store):
    conv = turn(store)
    art = persons_canvas(store, "một\nhai\nba", conv.id)
    past = await call(store, "artifact_read", {"id": art, "from_line": 4})
    assert past.output == TOOL_FAILED.format(
        error=ARTIFACT_READ_PAST_END.format(version=1, total=3)
    )
    image = store.artifacts.create("Ảnh", "image", "", USER, "", data=b"\x89PNG\r\n\x1a\n").id
    store.artifact_links.link(conv.id, image)
    result = await call(store, "artifact_read", {"id": image})
    assert result.output == TOOL_FAILED.format(error=ARTIFACT_READ_BINARY.format(kind="image"))


async def test_a_code_canvas_shows_its_language_beside_its_kind(store: Store):
    conv = turn(store)
    created = store.artifacts.create("Mã", "code", "", USER, "", "print(1)", language="python")
    store.artifact_links.link(conv.id, created.id)
    result = await call(store, "artifact_read", {"id": created.id})
    header = f"Canvas «Mã» (id {created.id}, v1, code python), dòng 1 / 1"
    assert result.output.split("\n") == [
        header,
        AUTHORS_PREFIX + "v1 người.",
        "print(1)",
        "Hết canvas.",
    ]
