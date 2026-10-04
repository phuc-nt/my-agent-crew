"""Which kind of canvas a workspace file becomes: its last suffix says, whatever its case. A
page comes in as a page that runs, a file of code brings its language, and a suffix that names
no kind is refused with the way out."""

from __future__ import annotations

import pytest

from my_agent_crew.artifacts.kinds import KINDS
from my_agent_crew.texts_canvas import IMPORT_UNKNOWN_SUFFIX
from my_agent_crew.tools.artifact_source import SourceError, code_language, infer_kind
from my_agent_crew.tools.registry import ToolError


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("notes/a.md", ("markdown", "")),
        ("A.MARKDOWN", ("markdown", "")),
        ("out/deck/index.html", ("html", "")),
        ("x.HTM", ("html", "")),
        ("logo.svg", ("svg", "")),
        ("flow.mmd", ("mermaid", "")),
        ("flow.Mermaid", ("mermaid", "")),
        ("a.png", ("image", "")),
        ("a.JPG", ("image", "")),
        ("a.jpeg", ("image", "")),
        ("a.gif", ("image", "")),
        ("a.webp", ("image", "")),
        ("conf.yml", ("code", "yaml")),
        ("conf.yaml", ("code", "yaml")),
        ("app.tsx", ("code", "tsx")),
        ("main.PY", ("code", "python")),
        ("style.css", ("code", "css")),
        ("notes.txt", ("code", "")),
        ("x.html.txt", ("code", "")),
    ],
)
def test_the_last_suffix_names_the_kind_whatever_its_case(path: str, expected: tuple[str, str]):
    assert infer_kind(path) == expected


@pytest.mark.parametrize("path", ["data.bin", "Makefile", "archive.tar.gz", "notes.md.bak"])
def test_a_suffix_that_names_no_kind_is_refused_with_a_hint_to_pass_one(path: str):
    with pytest.raises(SourceError) as caught:
        infer_kind(path)
    assert isinstance(caught.value, ToolError) and caught.value.status == 422
    assert str(caught.value) == IMPORT_UNKNOWN_SUFFIX.format(path=path, kinds=", ".join(KINDS))
    assert "`kind`" in str(caught.value)


def test_code_takes_its_language_from_the_suffix_and_none_from_one_it_does_not_know():
    names = ("deck.html", "a.YML", "notes.txt", "data.bin")
    assert [code_language(name) for name in names] == ["html", "yaml", "", ""]
