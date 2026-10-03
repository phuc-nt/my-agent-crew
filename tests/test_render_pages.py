"""The pages themselves: where the reporter goes in an html canvas and what it must not contain,
and how the mermaid page puts a diagram in front of the browser without letting its source run.
What the pages do in a browser is for the browser tests; here is what they are made of."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from html.parser import HTMLParser

import pytest

from my_agent_crew.artifacts.mermaid_page import (
    MERMAID_SRI,
    MERMAID_TAG,
    MERMAID_URL,
    MERMAID_VERSION,
    mermaid_page,
)
from my_agent_crew.artifacts.render import REPORTER_JS, REPORTER_TAG, html_page
from my_agent_crew.texts_canvas import RENDER_MERMAID_OFFLINE

TITLE = "Sơ đồ"
DIAGRAM = "graph TD\n  A --> B\n"
Element = tuple[str, dict[str, str | None], str]


class Page(HTMLParser):
    """What a browser's parser makes of a page: its doctype, comments and elements in the order
    it meets them, each with the text between its start and its end, or the next element. A
    doctype is named `!doctype` and a comment `!comment`."""

    def __init__(self, source: str) -> None:
        super().__init__()
        self.elements: list[Element] = []
        self._collecting = False
        self.feed(source)
        self.close()

    def handle_decl(self, decl: str) -> None:
        self.elements.append(("!doctype", {}, decl))
        self._collecting = False

    def handle_comment(self, data: str) -> None:
        self.elements.append(("!comment", {}, data))
        self._collecting = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.append((tag, dict(attrs), ""))
        self._collecting = True

    def handle_endtag(self, tag: str) -> None:
        self._collecting = False

    def handle_data(self, data: str) -> None:
        if self._collecting:
            name, attrs, text = self.elements[-1]
            self.elements[-1] = (name, attrs, text + data)

    def names(self) -> list[str]:
        return [name for name, _, _ in self.elements]

    def named(self, name: str) -> list[tuple[dict[str, str | None], str]]:
        return [(attrs, text) for found, attrs, text in self.elements if found == name]


LONG = "x" * 10_000
# What an engine from before 2015 cannot parse.
MODERN = re.compile(r"=>|\blet\b|\bconst\b|\bclass\b|\basync\b|\bawait\b|`|\?\.|\?\?")


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("<!doctype html>", "<html><body>x</body></html>"),
        ("<!DOCTYPE html>", "<p>x</p>"),
        ('<!DocType html PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://w3.org/strict.dtd">', "<p>"),
        ("﻿<!doctype html>", "<p>x</p>"),
        ("\n \t\n<!doctype html>", "\n<p>x</p>"),
        ("<!-- by an agent -->\n<!-- v2 --><!doctype html>", "<p>x</p>"),
        ("", "<h1>no doctype</h1>"),
        ("", ""),
        ("", "<p>x</p><!doctype html>"),
        ("", f"<!--{LONG}--><!doctype html><p>x</p>"),
        ("", f"<!doctype {LONG}"),
    ],
    ids=[
        "lowercase",
        "uppercase",
        "with identifiers",
        "after a byte order mark",
        "after blank space",
        "after comments",
        "none",
        "empty",
        "not at the start",
        "behind a long comment",
        "never closed",
    ],
)
def test_the_reporter_follows_a_doctype_that_begins_the_page_and_tops_a_page_without_one(
    before, after
):
    # A script ahead of the doctype leaves the page in quirks mode, and nothing but the reporter
    # may be added: taking it out gives back the canvas as it was written.
    assert html_page(before + after) == before + REPORTER_TAG + after


def test_a_browser_meets_the_doctype_first_and_the_reporter_before_the_pages_own_script():
    page = Page(html_page("<!doctype html><title>x</title><script>run()</script>"))
    assert page.names() == ["!doctype", "script", "title", "script"]
    assert page.named("script")[0] == ({}, REPORTER_JS)
    assert Page(html_page("<h1>x</h1>")).names() == ["script", "h1"]


def test_the_reporter_cannot_end_its_own_script_early():
    assert "</script" not in REPORTER_JS.lower()
    assert "<!--" not in REPORTER_JS


def test_the_reporter_is_old_plain_javascript_in_one_function_that_leaves_no_globals():
    # A page that does not parse reports nothing, and the reporter is the one thing that must.
    assert not MODERN.search(REPORTER_JS)
    assert REPORTER_JS.startswith("(function () {\n")
    assert REPORTER_JS.endswith("\n})();\n")


def test_a_rejection_that_is_a_plain_object_is_told_by_its_message():
    # Mermaid rejects a diagram it cannot parse with `{str, message, hash}`, not with an `Error`,
    # and `String()` of that is "[object Object]": the person would read nothing of their mistake.
    assert "report(reason(event.reason)" in REPORTER_JS
    assert "typeof value.message" in REPORTER_JS


@pytest.mark.parametrize(
    "make",
    [
        lambda: html_page("<!---->" * 28 + "x"),
        lambda: mermaid_page(TITLE, "```mermaid\n" + " " * 64_000 + "x"),
    ],
    ids=["comments before a doctype that is not there", "blanks in a fenced diagram"],
)
def test_the_work_on_a_page_does_not_grow_with_the_square_of_what_it_holds(
    make: Callable[[], str],
):
    # Both run on the event loop. Each took seconds, or for the comments forever, in a version
    # that tried every way to match: a canvas of the right shape would have frozen the server.
    started = time.perf_counter()
    make()
    assert time.perf_counter() - started < 0.5


def test_a_diagram_that_closes_the_pre_and_opens_a_script_is_drawn_as_text():
    source = "graph TD\n  A[</pre><script>alert(1)</script>] --> B\n"
    page = Page(mermaid_page(TITLE, source))
    assert [attrs.get("src") for attrs, _ in page.named("script")] == [None, MERMAID_URL, None]
    assert not [text for _, text in page.named("script") if "alert" in text]
    assert page.named("pre") == [({"class": "mermaid"}, source)]


def test_a_title_cannot_break_out_of_the_title_element():
    title = '</title><script>alert(1)</script>"&'
    page = Page(mermaid_page(title, DIAGRAM))
    assert page.named("title") == [({}, title)]
    assert len(page.named("script")) == 3


@pytest.mark.parametrize(
    ("source", "drawn"),
    [
        ("```mermaid\ngraph TD\n  A --> B\n```", "graph TD\n  A --> B"),
        ("```Mermaid  \ngraph TD\n```\n\n", "graph TD"),
        ("\n  ```mermaid\ngraph TD\n  A --> B\n  ```  \n", "graph TD\n  A --> B"),
        ("```mermaid\n```", ""),
        ("graph TD\n  A --> B\n", "graph TD\n  A --> B\n"),
        ("```mermaid\ngraph TD\n", "```mermaid\ngraph TD\n"),
        ("```python\nprint(1)\n```", "```python\nprint(1)\n```"),
        ("```mermaid```", "```mermaid```"),
        (
            "```mermaid\nsequenceDiagram\n  Note over A: ```\n  A->>B: hi\n```",
            "sequenceDiagram\n  Note over A: ```\n  A->>B: hi",
        ),
    ],
    ids=[
        "fenced",
        "fenced, any case, blanks around",
        "fenced and indented",
        "fenced and empty",
        "not fenced",
        "never closed",
        "another language",
        "on one line",
        "a fence inside the diagram",
    ],
)
def test_one_fence_around_the_whole_diagram_comes_off_the_page_and_nothing_else_does(source, drawn):
    assert Page(mermaid_page(TITLE, source)).named("pre") == [({"class": "mermaid"}, drawn)]


def test_the_diagram_library_is_one_pinned_version_checked_against_its_hash():
    page = Page(mermaid_page(TITLE, DIAGRAM))
    loaded = [attrs for attrs, _ in page.named("script") if "src" in attrs]
    assert loaded == [{"src": MERMAID_URL, "integrity": MERMAID_SRI, "crossorigin": "anonymous"}]
    # Never `latest`, never a major version alone: the hash belongs to the file of one release.
    assert re.fullmatch(r"\d+\.\d+\.\d+", MERMAID_VERSION)
    assert f"/mermaid@{MERMAID_VERSION}/" in MERMAID_URL
    assert re.fullmatch(r"sha384-[A-Za-z0-9+/]{64}", MERMAID_SRI)  # 48 bytes, no padding
    assert MERMAID_URL.startswith("https://cdn.jsdelivr.net/")


def test_the_library_is_told_not_to_run_what_a_diagram_carries():
    runner = Page(mermaid_page(TITLE, DIAGRAM)).named("script")[-1][1]
    assert 'securityLevel: "strict"' in runner
    assert "startOnLoad: false" in runner


def test_a_diagram_that_does_not_parse_is_left_to_the_reporter():
    # `run()` rejects a source Mermaid cannot read. Nothing on the page handles that rejection, so
    # it reaches the reporter as an unhandled one and the error bar says why nothing was drawn.
    runner = Page(mermaid_page(TITLE, DIAGRAM)).named("script")[-1][1]
    assert "\n  window.mermaid.run();\n" in runner
    assert not re.search(r"\b(?:try|catch|finally|await)\b|\.then\(", runner)


def test_without_the_library_the_page_says_so_above_the_source():
    page = Page(mermaid_page(TITLE, DIAGRAM))
    [(attrs, text)] = [(attrs, text) for attrs, text in page.named("p")]
    assert (attrs["id"], "hidden" in attrs, text) == ("offline", True, RENDER_MERMAID_OFFLINE)
    assert 'getElementById("offline").hidden = false' in page.named("script")[-1][1]


def test_the_page_is_a_whole_document_that_reports_before_it_loads_anything():
    text = mermaid_page(TITLE, DIAGRAM)
    page = Page(text)
    assert text.startswith('<!doctype html>\n<html lang="vi">\n')
    assert page.names()[0] == "!doctype"
    assert page.named("script")[0] == ({}, REPORTER_JS)
    assert text.index(REPORTER_TAG) < text.index(MERMAID_TAG)
    assert page.named("title") == [({}, TITLE)]
