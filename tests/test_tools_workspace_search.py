from pathlib import Path

import pytest

from my_agent_crew.tools import workspace_search
from my_agent_crew.tools.registry import ToolError
from my_agent_crew.tools.workspace_search import build_search_tools, search_in_tree


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def start():\n    return 1\n", encoding="utf-8")
    (tmp_path / "src" / "util.py").write_text("def helper():\n    pass\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("start here\n", encoding="utf-8")
    noise = tmp_path / "node_modules" / "pkg"
    noise.mkdir(parents=True)
    (noise / "index.js").write_text("def start(){}\n", encoding="utf-8")
    return tmp_path


def tools(root: Path):
    return {tool.name: tool for tool in build_search_tools(root)}


def test_search_in_tree_finds_lines_and_skips_vendored_directories(tree: Path):
    hits = search_in_tree(tree, r"def start", None, 50)
    assert [h.split(":")[0] for h in hits] == ["src/app.py"]
    assert "node_modules" not in "\n".join(hits)


def test_search_in_tree_filters_by_glob_and_caps_results(tree: Path):
    assert search_in_tree(tree, "start", "*.md", 50)[0].startswith("notes.md:1")
    assert len(search_in_tree(tree, ".", None, 2)) == 2


def test_search_in_tree_skips_binary_files(tmp_path: Path):
    (tmp_path / "blob.bin").write_bytes(b"start\x00\x01binary")
    assert search_in_tree(tmp_path, "start", None, 10) == []


def test_search_in_tree_rejects_a_broken_pattern(tmp_path: Path):
    with pytest.raises(ToolError, match="Mẫu tìm kiếm sai"):
        search_in_tree(tmp_path, "([", None, 10)


async def test_grep_tool_works_without_ripgrep(tree: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(workspace_search.shutil, "which", lambda _: None)
    out = await tools(tree)["workspace_grep"].run({"pattern": "helper"})
    assert out.startswith("src/util.py:1")
    empty = await tools(tree)["workspace_grep"].run({"pattern": "nothing-here"})
    assert empty == "Không có dòng nào khớp."


async def test_grep_tool_uses_ripgrep_when_present(tree: Path):
    import shutil as real_shutil

    if not real_shutil.which("rg"):
        pytest.skip("ripgrep not installed")
    out = await tools(tree)["workspace_grep"].run({"pattern": "helper"})
    assert "util.py" in out and "node_modules" not in out


async def test_glob_tool_lists_matching_files_only(tree: Path):
    out = await tools(tree)["workspace_glob"].run({"pattern": "*.py"})
    assert sorted(out.splitlines()) == ["src/app.py", "src/util.py"]
    assert await tools(tree)["workspace_glob"].run({"pattern": "*.rs"}) == "Không có tệp nào khớp."


async def test_search_tools_refuse_a_path_outside_the_workspace(tree: Path):
    with pytest.raises(ToolError, match="ngoài thư mục làm việc"):
        await tools(tree)["workspace_glob"].run({"pattern": "*", "path": "../.."})
