"""`artifact_import` with no `id`: a file already in the workspace becomes a canvas without its
text passing through the model. The canvas remembers where it came from, the conversation that
imported it has seen it and shares it, and the result names the file, its size and a digest,
never a word the file holds."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from my_agent_crew.agent.turn_context import CHAT, set_turn_conversation, set_turn_source
from my_agent_crew.artifacts.tag import artifact_tag
from my_agent_crew.store.db import Store
from my_agent_crew.tools.artifact_file_texts import (
    IMPORT_CREATED,
    IMPORT_RELATIVE_REFS,
    IMPORT_SOURCE,
    IMPORT_SOURCE_READABLE,
    SOURCE_WORKSPACE,
)
from my_agent_crew.tools.registry import ToolResult
from tests.canvas_helpers import PNG, call, child_turn, put, seen, tagged, turn

MENU = "# Thực đơn\nthứ hai: phở\nthứ ba: bún chả\n"
MARK = "CHU-RIENG-CUA-TEP"
PAGE = (
    f'<link rel="stylesheet" href="{MARK}.css"><img src="{MARK}/a.png">'
    f'<img src="data:image/png;base64,AAAA"><a href="#{MARK}">{MARK}</a>\n'
)
DRAWING = '<svg xmlns="http://www.w3.org/2000/svg"><image href="anh.png"/></svg>\n'
LINKS = '# Ghi chú\n![a](anh.png)\n<img src="anh.png">\n'


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    put(workspace, "notes/thuc-don.md", MENU)
    put(workspace, "out/deck/index.html", PAGE)
    return workspace


async def _import(store: Store, root: Path, path: str, **args: object) -> ToolResult:
    return await call(store, "artifact_import", {"path": path, **args}, root=root)


def _workspace(path: str, readable: bool = True) -> str:
    line = IMPORT_SOURCE_READABLE if readable else IMPORT_SOURCE
    return line.format(source=SOURCE_WORKSPACE.format(path=path))


def _told(art: str, path: str, title: str, kind: str, payload: bytes, *more: str) -> str:
    """What a first import answers: the tag, the file by name, size and digest, then `more`."""
    size, digest = len(payload), hashlib.sha256(payload).hexdigest()[:12]
    done = IMPORT_CREATED.format(path=path, title=title, kind=kind, size=size, digest=digest)
    return "\n".join([artifact_tag(art, 1), done, *more])


async def test_a_file_becomes_a_canvas_that_remembers_where_it_came_from(store: Store, root: Path):
    conv = turn(store)
    result = await _import(store, root, "notes/thuc-don.md")
    art, version, unchanged = tagged(result)
    summary, head = store.artifacts.get(art), store.artifacts.head(art)
    assert (version, unchanged, summary.head_version, seen(store, conv, art)) == (1, False, 1, 1)
    assert (summary.title, summary.kind, summary.language) == ("thuc-don", "markdown", "")
    assert (summary.agent_id, summary.source) == ("coach", "workspace:coach/notes/thuc-don.md")
    assert (head.content, head.author, head.conversation_id) == (MENU, "agent:coach", conv.id)
    told = _told(art, "notes/thuc-don.md", "thuc-don", "markdown", MENU.encode())
    assert result.output == f"{told}\n{_workspace('notes/thuc-don.md')}"
    assert str(root.parent) not in result.output


async def test_a_child_shares_what_it_imports_with_the_root_of_its_chain(store: Store, root: Path):
    top = store.create()
    child = child_turn(store, top)
    art, _, _ = tagged(await _import(store, root, "notes/thuc-don.md"))
    for conv in (child, top):
        link = store.artifact_links.get(conv.id, art)
        assert link is not None and link.shared, conv.id
    assert (seen(store, child, art), seen(store, top, art)) == (1, 0)


@pytest.mark.parametrize(
    ("path", "args", "title"),
    [
        ("notes/thuc-don.md", {}, "thuc-don"),
        ("out/deck/index.html", {}, "deck"),
        ("index.html", {}, "index"),
        ("out/Báo cáo.v2.md", {}, "Báo cáo.v2"),
        ("a" * 199 + "e\u0301b.md", {}, "a" * 199 + "\u00e9"),
        ("notes/thuc-don.md", {"title": "Thực đơn tuần"}, "Thực đơn tuần"),
        ("notes/thuc-don.md", {"title": "  "}, "thuc-don"),
    ],
)
async def test_a_canvas_is_titled_after_its_file_unless_a_title_is_sent(
    store: Store, root: Path, path: str, args: dict[str, str], title: str
):
    """An index page is named after its folder, never after the workspace itself; a long name
    is cut to what a title may hold, on whole letters."""
    put(root, path, PAGE if path.endswith(".html") else MENU)
    turn(store)
    art, _, _ = tagged(await _import(store, root, path, **args))
    assert store.artifacts.get(art).title == title


async def test_the_result_tells_of_a_page_without_a_word_the_file_holds(store: Store, root: Path):
    """Whoever wrote the file must not put words into what the model reads back from the tool:
    not through its text, and not through the files it points at, which are only counted."""
    turn(store)
    path = "out/deck/index.html"
    result = await _import(store, root, path)
    art, _, _ = tagged(result)
    warning = IMPORT_RELATIVE_REFS.format(count=2)
    told = _told(art, path, "deck", "html", PAGE.encode(), _workspace(path), warning)
    assert result.output == told
    assert MARK not in result.output and str(root.parent) not in result.output
    assert store.artifacts.head(art).content == PAGE


async def test_only_a_page_and_a_drawing_are_warned_of_the_files_they_point_at(
    store: Store, root: Path
):
    """A canvas loads nothing from beside the page; markdown and code show their text as it is."""
    put(root, "logo.svg", DRAWING)
    put(root, "notes/links.md", LINKS)
    turn(store)
    drawing = await _import(store, root, "logo.svg")
    assert drawing.output.split("\n")[3:] == [IMPORT_RELATIVE_REFS.format(count=1)]
    for path, args in (("notes/links.md", {}), ("out/deck/index.html", {"kind": "code"})):
        plain = await _import(store, root, path, **args)
        assert tagged(plain)[1] == 1 and len(plain.output.split("\n")) == 3, path


@pytest.mark.parametrize(
    ("path", "args", "expected"),
    [
        ("out/deck/index.html", {"kind": "code", "language": "html"}, ("code", "html")),
        ("out/deck/index.html", {"kind": "code"}, ("code", "html")),
        ("out/deck/index.html", {"kind": "code", "language": "jinja"}, ("code", "jinja")),
        ("notes/todo.txt", {"kind": "code"}, ("code", "")),
        ("src/app.py", {}, ("code", "python")),
        ("README", {"kind": "markdown"}, ("markdown", "")),
        ("notes/thuc-don.md", {"kind": "", "id": "", "source_url": ""}, ("markdown", "")),
    ],
)
async def test_a_kind_sent_wins_over_the_suffix_and_code_takes_its_language_from_it(
    store: Store, root: Path, path: str, args: dict[str, str], expected: tuple[str, str]
):
    """A page's source comes in as text to edit when asked for as code. An optional argument
    sent blank counts as one left out."""
    put(root, path, PAGE)
    turn(store)
    result = await _import(store, root, path, **args)
    summary = store.artifacts.get(tagged(result)[0])
    assert (summary.kind, summary.language) == expected
    label = " ".join(part for part in expected if part)
    assert f"({label}, {len(PAGE.encode())} byte" in result.output


async def test_a_picture_comes_in_byte_for_byte_and_is_not_offered_for_reading(
    store: Store, root: Path
):
    put(root, "img/logo.png", PNG)
    turn(store)
    result = await _import(store, root, "img/logo.png")
    art, _, _ = tagged(result)
    head = store.artifacts.head(art)
    assert (store.artifacts.get(art).kind, head.content, head.data) == ("image", None, PNG)
    source = _workspace("img/logo.png", readable=False)
    assert result.output == _told(art, "img/logo.png", "logo", "image", PNG, source)


async def test_a_link_to_the_original_is_kept_as_the_source(store: Store, root: Path):
    """The file is only an export of something that lives elsewhere."""
    turn(store)
    url = "https://docs.example.com/deck?id=1"
    result = await _import(store, root, "notes/thuc-don.md", source_url=url)
    assert store.artifacts.get(tagged(result)[0]).source == url
    assert result.output.split("\n")[2] == IMPORT_SOURCE_READABLE.format(source=url)


async def test_an_absolute_path_inside_the_workspace_is_stored_relative_to_it(
    store: Store, root: Path
):
    """What the canvas keeps and shows never says where the workspace sits on this machine."""
    turn(store)
    result = await _import(store, root, str(root / "notes" / "thuc-don.md"))
    art = tagged(result)[0]
    assert store.artifacts.get(art).source == "workspace:coach/notes/thuc-don.md"
    told = _told(art, "notes/thuc-don.md", "thuc-don", "markdown", MENU.encode())
    assert result.output == f"{told}\n{_workspace('notes/thuc-don.md')}"
