"""How a canvas names where it came from: a path with nothing hidden in it, the agent whose
workspace holds the file, or a plain web link to the original; and how many files a page
points at that a canvas will not load."""

from __future__ import annotations

from pathlib import Path

import pytest

from my_agent_crew.tools.artifact_file_texts import IMPORT_BAD_PATH, IMPORT_BAD_URL
from my_agent_crew.tools.artifact_source_ref import (
    PATH_MAX,
    URL_MAX,
    check_path,
    parse_source,
    relative_ref_count,
    source_for,
    web_url,
)
from my_agent_crew.tools.registry import ToolError

BAD_PATH = IMPORT_BAD_PATH.format(limit=PATH_MAX)
LONG_URL = "https://example.com/" + "a" * (URL_MAX - len("https://example.com/"))
PAGE = """
<link rel="stylesheet" href="style.css"><script src='app.js'></script>
<img src=img/a.png alt=""><img SRC="img/a.png"><a href="/api/assets/x.png">tệp</a>
<svg><use xlink:href="sprite.svg#a"/></svg>
<a href="#top">đầu</a><a href="https://x.example/">ngoài</a><a href="HTTP://x.example/">ngoài</a>
<img src="data:image/png;base64,AAAA"><img src="blob:abc"><script src="//cdn.example/x.js"></script>
<a href="mailto:a@b.example">thư</a><a href="javascript:void(0)">nút</a><a href=" ">rỗng</a>
"""


@pytest.mark.parametrize(
    "path",
    [
        "a\x00.md",
        "a\nb.md",
        "a\x1b[0m.md",
        "a\x7f.md",
        "a\u202e.md",
        "a\u200f.md",
        "a\u200b.md",
        "a\u2028.md",
        "a\u2029.md",
        "x" * (PATH_MAX + 1),
        "",
        "   ",
    ],
)
def test_a_path_that_hides_something_is_too_long_or_is_blank_is_refused(path: str):
    with pytest.raises(ToolError) as caught:
        check_path(path)
    assert str(caught.value) == BAD_PATH


@pytest.mark.parametrize(
    "path", ["notes/thực đơn.md", "out/deck/index.html", "/abs/a b.md", "~/a.md", "x" * PATH_MAX]
)
def test_an_ordinary_path_passes_as_sent(path: str):
    assert check_path(path) == path


def test_a_source_names_the_agent_and_the_path_under_its_workspace(tmp_path: Path):
    """Told back apart at the first slash: an agent id holds none, a path may hold any."""
    root = tmp_path / "ws"
    root.mkdir()
    link = tmp_path / "link"
    link.symlink_to(root)
    file = root.resolve() / "out" / "a:b" / "index.html"
    source = source_for("health-coach", link, file)
    assert source == "workspace:health-coach/out/a:b/index.html"
    assert parse_source(source) == ("health-coach", "out/a:b/index.html")


def test_a_source_is_never_built_from_a_name_that_hides_something(tmp_path: Path):
    """The path sent was checked, but the name on disk is what the source keeps."""
    with pytest.raises(ToolError) as caught:
        source_for("coach", tmp_path, tmp_path.resolve() / "a\u202eb.md")
    assert str(caught.value) == BAD_PATH


@pytest.mark.parametrize(
    "source",
    [
        "",
        "https://example.com/a.md",
        "workspace:",
        "workspace:coach",
        "workspace:coach/",
        "workspace:/a.md",
        "workspace:Coach/a.md",
        "workspace:co ach/a.md",
        "file:coach/a.md",
        "coach/a.md",
    ],
)
def test_a_source_that_names_no_workspace_file_parses_to_nothing(source: str):
    assert parse_source(source) is None


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://example.com/a?b=c#d",
        "HTTPS://Example.com/x",
        "https://example.com:8443/p",
        "https://vi.wikipedia.org/wiki/Phở",
        LONG_URL,
    ],
)
def test_a_plain_web_link_passes_as_sent(url: str):
    assert web_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,<p>x</p>",
        "file:///etc/hosts",
        "ftp://example.com/a",
        "https://",
        "http:///path",
        "https:example.com",
        "//example.com/a",
        "example.com",
        "https://exa mple.com",
        "https://example.com/a\nb",
        " https://example.com",
        "https://example.com/\u202e",
        "http://[::1",
        LONG_URL + "a",
        "",
    ],
)
def test_a_link_that_is_not_a_plain_web_address_is_refused(url: str):
    with pytest.raises(ToolError) as caught:
        web_url(url)
    assert str(caught.value) == IMPORT_BAD_URL.format(limit=URL_MAX)


def test_each_file_a_page_points_at_is_counted_once_and_a_link_that_loads_none_is_not():
    """style.css, app.js, img/a.png, /api/assets/x.png and sprite.svg#a."""
    assert relative_ref_count(PAGE) == 5
    assert relative_ref_count("# Ghi chú\nkhông có đường dẫn nào") == 0
