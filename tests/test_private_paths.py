"""Folders the server keeps private: no file tool is given a path that leads into one, by a
name, by a link, by another spelling, or by a walk that started above it."""

from __future__ import annotations

import shutil
import unicodedata
from pathlib import Path

import pytest

from my_agent_crew import texts
from my_agent_crew.tools import private_paths, workspace_search
from my_agent_crew.tools.private_paths import is_private, keep_private, kept_under
from my_agent_crew.tools.registry import ToolError
from my_agent_crew.tools.workspace import build_workspace_tools, resolve_inside, resolve_writable
from my_agent_crew.tools.workspace_search import build_search_tools, search_in_tree


@pytest.fixture
def home(tmp_path: Path) -> Path:
    """A crew home with a browser folder that holds one agent's logins, a workspace beside
    it, and a word to search for on both sides."""
    home = tmp_path / "home"
    (home / "browser" / "coach").mkdir(parents=True)
    (home / "browser" / "coach" / "Cookies").write_text("khoa = bimat\n", encoding="utf-8")
    (home / "inbox").mkdir()
    (home / "inbox" / "note.md").write_text("khoa cua tu\n", encoding="utf-8")
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "plan.md").write_text("khoa hoc\n", encoding="utf-8")
    return home


def folds_case(folder: Path) -> bool:
    (folder / "probe-a").touch()
    return (folder / "PROBE-A").exists()


def files_of(hits: list[str]) -> set[str]:
    return {hit.split(":")[0].removeprefix("./") for hit in hits}


def test_nothing_is_private_until_a_folder_is_kept(home: Path):
    assert not is_private(home / "browser" / "coach" / "Cookies")
    assert kept_under(home) == []
    assert resolve_inside(home, "browser/coach/Cookies").name == "Cookies"


def test_a_kept_folder_and_all_below_it_are_private_and_nothing_beside_it(home: Path):
    keep_private(home / "browser")
    (home / "browsers").mkdir()

    assert is_private(home / "browser")
    assert is_private(home / "browser" / "coach")
    assert is_private(home / "browser" / "coach" / "Cookies")
    assert is_private(home / "browser" / "chưa" / "có" / "gì")
    assert is_private(home / "inbox" / ".." / "browser" / "coach")
    for open_path in (home, home.parent, home / "inbox" / "note.md", home / "browsers" / "x"):
        assert not is_private(open_path), open_path
    assert not is_private(home / "nothing" / "here")


def test_a_link_into_a_kept_folder_is_private_wherever_it_lies(home: Path, tmp_path: Path):
    keep_private(home / "browser")
    work = tmp_path / "work"
    (work / "tep").symlink_to(home / "browser" / "coach" / "Cookies")
    (work / "muc").symlink_to(home / "browser" / "coach")
    (work / "nha").symlink_to(home)
    (work / "hai").symlink_to(work / "muc")
    (work / "ngoai").symlink_to(home / "inbox")

    for led in ("tep", "muc", "muc/Cookies", "nha/browser", "nha/browser/coach/Cookies", "hai/x"):
        assert is_private(work / led), led
    for open_path in ("nha", "nha/inbox/note.md", "ngoai/note.md", "plan.md"):
        assert not is_private(work / open_path), open_path


def test_a_kept_folder_is_known_by_what_it_is_not_by_how_it_is_spelt(home: Path, tmp_path: Path):
    keep_private(home / "browser")
    folds = folds_case(tmp_path)

    # Where the file system folds case the other spelling is the same folder, and is refused;
    # where it does not, it is another folder and nobody's logins.
    assert is_private(home / "BROWSER" / "coach" / "Cookies") is folds
    assert is_private(home.parent / "HOME" / "Browser") is folds


def test_a_folder_kept_before_it_is_made_is_known_by_its_name_under_what_is_there(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    (tmp_path / "alias").symlink_to(home)
    keep_private(home / "browser")
    keep_private(home / "sau" / "nua")
    keep_private(home / unicodedata.normalize("NFC", "hồ sơ"))

    assert is_private(home / "browser")
    assert is_private(home / "browser" / "coach" / "Cookies")
    assert is_private(home / "Browser" / "coach")  # a name not on disk yet folds like one that is
    assert is_private(tmp_path / "alias" / "browser" / "x")
    assert is_private(home / "sau" / "nua" / "x") and is_private(home / "sau" / "NUA")
    # And a name is the same name however its accents are put together.
    assert is_private(home / unicodedata.normalize("NFD", "hồ sơ") / "x")
    for open_path in ("browsers", "x/browser", "sau", "sau/khac", "nua", "sau/x/nua"):
        assert not is_private(home / open_path), open_path
    assert not is_private(home) and not is_private(tmp_path / "browser")

    (home / "browser").mkdir()
    assert is_private(home / "browser" / "coach") and not is_private(home / "browsers")
    (home / "sau").mkdir()
    assert is_private(home / "sau" / "nua" / "x") and not is_private(home / "sau" / "khac")


def test_kept_under_names_each_kept_folder_from_the_folder_above_it(home: Path, tmp_path: Path):
    (tmp_path / "alias").symlink_to(home)
    keep_private(home / "browser")
    # Kept under another name of the home, it is still told by where it really lies; and one
    # whose own folder is not made yet lies under nothing that is not there either.
    keep_private(tmp_path / "alias" / "a[1]" / "b")

    assert kept_under(home) == ["a[1]/b", "browser"]
    assert kept_under(tmp_path / "alias") == ["a[1]/b", "browser"]
    assert kept_under(tmp_path) == ["home/a[1]/b", "home/browser"]
    assert kept_under(tmp_path / "work") == []
    assert kept_under(home / "browser") == []
    assert kept_under(tmp_path / "nowhere") == []


def test_no_path_a_file_tool_resolves_leads_into_a_kept_folder(home: Path, tmp_path: Path):
    keep_private(home / "browser")
    work = tmp_path / "work"
    (work / "muc").symlink_to(home / "browser" / "coach")
    (tmp_path / "alias").symlink_to(home)
    inside = str(home / "browser" / "coach" / "Cookies")

    # By a name under a root that holds the folder, by an absolute path, by a link that lies
    # in the workspace, and by a path that only lands in the root once its links are read.
    for root, path in (
        (home, "browser"),
        (home, "browser/coach/Cookies"),
        (home, "inbox/../browser/coach"),
        (home, inside),
        (work, "muc"),
        (work, "muc/Cookies"),
        (home, str(tmp_path / "alias" / "browser" / "coach" / "Cookies")),
    ):
        with pytest.raises(ToolError) as refused:
            resolve_inside(root, path)
        assert str(refused.value) == texts.WORKSPACE_PRIVATE, path
        with pytest.raises(ToolError) as refused:
            resolve_writable(root, path)
        assert str(refused.value) == texts.WORKSPACE_PRIVATE, path

    # What is beside it resolves as before, and what is outside is still an escape.
    assert resolve_inside(home, "inbox/note.md") == home.resolve() / "inbox" / "note.md"
    assert resolve_inside(work, "plan.md") == work.resolve() / "plan.md"
    assert resolve_inside(home, str(tmp_path / "alias" / "inbox")) == home.resolve() / "inbox"
    with pytest.raises(ToolError) as refused:
        resolve_inside(work, inside)
    assert str(refused.value) == texts.WORKSPACE_ESCAPE


async def test_the_file_tools_neither_read_list_nor_write_a_kept_folder(home: Path):
    keep_private(home / "browser")
    tools = {tool.name: tool for tool in build_workspace_tools(home)}

    for name, args in (
        ("workspace_read", {"path": "browser/coach/Cookies"}),
        ("workspace_list", {"path": "browser"}),
        ("workspace_write", {"path": "browser/coach/Cookies", "content": "x"}),
        ("workspace_write", {"path": "browser/moi/Cookies", "content": "x"}),
    ):
        with pytest.raises(ToolError) as refused:
            await tools[name].run(args)
        assert str(refused.value) == texts.WORKSPACE_PRIVATE, name
    assert (home / "browser" / "coach" / "Cookies").read_text(encoding="utf-8") == "khoa = bimat\n"
    assert not (home / "browser" / "moi").exists()
    assert "khoa cua tu" in await tools["workspace_read"].run({"path": "inbox/note.md"})


def test_a_search_that_starts_above_a_kept_folder_walks_round_it(home: Path, tmp_path: Path):
    keep_private(home / "browser")
    work = tmp_path / "work"
    (work / "tep").symlink_to(home / "browser" / "coach" / "Cookies")
    (work / "ghi").symlink_to(home / "inbox" / "note.md")

    assert files_of(search_in_tree(home, "khoa", None, 50)) == {"inbox/note.md"}
    # A file that is a link is read like any other, unless what it leads to is kept.
    assert files_of(search_in_tree(work, "khoa", None, 50)) == {"ghi", "plan.md"}
    assert files_of(search_in_tree(tmp_path, "khoa", None, 50)) == {
        "home/inbox/note.md",
        "work/ghi",
        "work/plan.md",
    }


async def test_the_search_tools_leave_a_kept_folder_out_with_or_without_ripgrep(
    home: Path, monkeypatch: pytest.MonkeyPatch
):
    keep_private(home / "browser")
    # A folder that only shares the name, further down, is nobody's logins.
    (home / "inbox" / "browser").mkdir()
    (home / "inbox" / "browser" / "ghi.txt").write_text("khoa nay\n", encoding="utf-8")
    tools = {tool.name: tool for tool in build_search_tools(home)}
    globs = (None, "*", "**", "browser/**", "**/Cookies", "!inbox/")
    beside = {"inbox/note.md", "inbox/browser/ghi.txt"}

    found = await tools["workspace_glob"].run({"pattern": "*"})
    assert set(found.splitlines()) == beside
    with pytest.raises(ToolError) as refused:
        await tools["workspace_grep"].run({"pattern": "khoa", "path": "browser"})
    assert str(refused.value) == texts.WORKSPACE_PRIVATE

    for ripgrep in (True, False):
        if ripgrep and not shutil.which("rg"):
            continue
        if not ripgrep:
            monkeypatch.setattr(workspace_search.shutil, "which", lambda _: None)
        for glob in globs:
            args = {"pattern": "khoa"} | ({"glob": glob} if glob else {})
            out = await tools["workspace_grep"].run(args)
            assert "bimat" not in out and "Cookies" not in out, (ripgrep, glob)
        out = await tools["workspace_grep"].run({"pattern": "khoa"})
        assert files_of(out.splitlines()) == beside, ripgrep


async def test_ripgrep_is_told_a_kept_folder_by_a_name_it_cannot_read_as_a_pattern(tmp_path: Path):
    if not shutil.which("rg"):
        pytest.skip("ripgrep not installed")
    # On disk the folder is spelt one way and kept under another where case folds; and a
    # name full of pattern characters is still that one folder and no other.
    spelt = "Browser" if folds_case(tmp_path) else "browser"
    odd = tmp_path / "a[1]" / "b*"
    for folder in (tmp_path / spelt, odd, tmp_path / "a1" / "bc"):
        folder.mkdir(parents=True)
        (folder / "tep.txt").write_text("khoa\n", encoding="utf-8")
    keep_private(tmp_path / "browser")
    keep_private(odd)
    tools = {tool.name: tool for tool in build_search_tools(tmp_path)}

    out = await tools["workspace_grep"].run({"pattern": "khoa"})

    assert files_of(out.splitlines()) == {"a1/bc/tep.txt"}


def test_a_test_starts_with_no_folder_kept(tmp_path: Path):
    """A server keeps its folders for as long as it lives, and hundreds of tests build one:
    each starts with none, whatever the tests before it in this file kept."""
    assert private_paths._kept == set()
    keep_private(tmp_path)
