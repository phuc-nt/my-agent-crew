"""`artifact_export`: a version of a canvas goes out to a workspace file without its text
passing through the model. Text leaves as UTF-8 with LF line ends and a picture byte for byte;
the canvas stays as it was and what the conversation has seen does not move; and the tool
asks first, since it writes over a file that nothing keeps a version of."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from my_agent_crew.agent.turn_context import (
    CHAT,
    canvas_writes,
    set_turn_conversation,
    set_turn_source,
)
from my_agent_crew.artifacts.kinds import KINDS
from my_agent_crew.artifacts.tag import TAG_RE
from my_agent_crew.store.artifact_models import USER
from my_agent_crew.store.db import Store
from my_agent_crew.texts import TOOL_FAILED
from my_agent_crew.texts_canvas import (
    ARTIFACT_NOT_FOUND,
    ARTIFACT_REWRITE_UNSEEN,
    ARTIFACT_VERSION_GONE,
)
from my_agent_crew.tools.artifact_file_texts import EXPORT_DONE, EXPORT_REPLACED
from my_agent_crew.tools.artifact_files import build_artifact_file_tools
from my_agent_crew.tools.registry import ToolResult
from tests.canvas_helpers import (
    PLAN,
    PNG,
    SWIM,
    agents_canvas,
    call,
    created,
    persons_canvas,
    seen,
    turn,
)


@pytest.fixture(autouse=True)
def fresh_turn() -> Iterator[None]:
    yield
    set_turn_source(CHAT)
    set_turn_conversation("")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "ws").mkdir()
    return tmp_path / "ws"


async def _export(store: Store, root: Path, art: str, path: str, **args: object) -> ToolResult:
    return await call(store, "artifact_export", {"id": art, "path": path, **args}, root=root)


def _failed(message: str) -> str:
    return TOOL_FAILED.format(error=message)


def test_the_two_file_tools_come_together_and_only_the_export_asks_first(
    store: Store, tmp_path: Path
):
    """An import adds a version a person can go back from; an export writes over a file."""
    tools = build_artifact_file_tools(store, "coach", False, 8000, tmp_path, ())
    assert [tool.name for tool in tools] == ["artifact_import", "artifact_export"]
    assert [tool.requires_approval for tool in tools] == [False, True]
    assert not any(tool.parallel or tool.ask_reason for tool in tools)
    taking, giving = (tool.parameters for tool in tools)
    assert (taking["required"], giving["required"]) == (["path"], ["id", "path"])
    assert taking["properties"]["kind"]["enum"] == list(KINDS)
    names = {"path", "id", "title", "kind", "language", "source_url", "replace"}
    assert (set(taking["properties"]), set(giving["properties"])) == (
        names,
        {"id", "path", "version"},
    )


async def test_text_goes_out_as_utf8_and_the_canvas_stays_as_it_was(store: Store, root: Path):
    """The result opens with no canvas tag: a tag is the mark of a write a canvas kept. It
    says a file was replaced only when one was there."""
    turn(store)
    art = await created(store, PLAN)
    path = "notes/out/x.md"
    result = await _export(store, root, art, path)
    assert (root / path).read_bytes() == PLAN.encode("utf-8")
    size = len(PLAN.encode("utf-8"))
    done = EXPORT_DONE.format(version=1, id=art, title="Kế hoạch", size=size, path=path)
    assert (result.ok, result.output) == (True, done)
    assert TAG_RE.match(result.output) is None
    again = await _export(store, root, art, path)
    assert again.output == done + EXPORT_REPLACED
    assert (store.artifacts.get(art).head_version, canvas_writes(art)) == (1, 0)


async def test_a_picture_goes_out_byte_for_byte(store: Store, root: Path):
    conv = turn(store)
    art = store.artifacts.create("Logo", "image", "", USER, "", data=PNG).id
    store.artifact_links.link(conv.id, art)
    result = await _export(store, root, art, "out/logo.png")
    assert (root / "out" / "logo.png").read_bytes() == PNG
    done = EXPORT_DONE.format(version=1, id=art, title="Logo", size=len(PNG), path="out/logo.png")
    assert result.output == done


async def test_a_page_goes_out_under_exactly_the_name_asked_for(store: Store, root: Path):
    """The suffix is the caller's to choose; the tool adds none and changes none. A path sent
    from the top of the machine is named back from the workspace."""
    turn(store)
    art = agents_canvas(store, "coach", "<p>chào</p>\n", kind="html")
    result = await _export(store, root, art, str(root / "x.html"))
    assert result.ok and result.output.endswith(" ra x.html.")
    assert str(root.parent) not in result.output
    assert [entry.name for entry in root.iterdir()] == ["x.html"]
    assert (root / "x.html").read_text(encoding="utf-8") == "<p>chào</p>\n"


async def test_an_older_version_goes_out_when_asked_for_and_one_that_is_gone_is_said_so(
    store: Store, root: Path
):
    turn(store)
    art = await created(store, PLAN)
    store.artifacts.write(art, SWIM, USER, "")
    for version, number, text in ((1, 1, PLAN), ("1", 1, PLAN), (2, 2, SWIM), (None, 2, SWIM)):
        result = await _export(store, root, art, "x.md", version=version)
        assert result.ok and result.output.startswith(f"Đã xuất v{number} "), version
        assert (root / "x.md").read_text(encoding="utf-8") == text, version
    gone = await _export(store, root, art, "y.md", version=9)
    assert gone.output == _failed(ARTIFACT_VERSION_GONE.format(version=9, head=2, id=art))
    assert not (root / "y.md").exists()


async def test_a_canvas_out_of_reach_reads_as_one_that_does_not_exist_and_no_file_is_made(
    store: Store, root: Path
):
    turn(store)
    art = agents_canvas(store, "ledger", "# Sổ\n")
    result = await _export(store, root, art, "x.md")
    assert result.output == _failed(ARTIFACT_NOT_FOUND.format(id=art))
    assert list(root.iterdir()) == []


async def test_an_export_makes_nothing_seen_so_an_unread_canvas_still_cannot_be_rewritten(
    store: Store, root: Path
):
    """Carrying the text out is not reading it. The canvas is shared with the conversation,
    as one it worked with, and nothing else about it moves."""
    conv = turn(store)
    art = persons_canvas(store, PLAN, conv.id)
    assert (await _export(store, root, art, "x.md")).ok
    assert seen(store, conv, art) == 0
    rewrite = await call(store, "artifact_rewrite", {"id": art, "content": "mới"}, root=root)
    assert rewrite.output == _failed(ARTIFACT_REWRITE_UNSEEN.format(id=art))
    link = store.artifact_links.get(conv.id, art)
    assert link is not None and link.shared
    assert store.artifacts.head(art).content == PLAN
