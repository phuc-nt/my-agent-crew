"""The name a canvas is saved under when it is downloaded: its title in any script, less what
a file system refuses, and the extension of its kind."""

import pytest

from my_agent_crew.artifacts.filenames import FILENAME_MAX, filename_for


@pytest.mark.parametrize(
    ("title", "stem"),
    [
        ("Kế hoạch tuần", "Kế hoạch tuần"),
        ("báo cáo/2026\\10", "báo cáo-2026-10"),
        ('Kế "hoạch"\n\tmới\x00', "Kế hoạch mới"),
        ("a: b? <c> | d*", "a b c d"),
        ("  ..ẩn.  ", "ẩn"),
        ("x" * (FILENAME_MAX + 1), "x" * FILENAME_MAX),
        ("x" * (FILENAME_MAX - 1) + " yz", "x" * (FILENAME_MAX - 1)),
        ("", "canvas"),
        ('/"\n', "canvas"),
    ],
)
def test_a_file_name_keeps_the_title_in_any_script_without_what_a_file_system_refuses(title, stem):
    assert filename_for(title, "markdown") == stem + ".md"


@pytest.mark.parametrize(
    ("kind", "language", "extension"),
    [
        ("markdown", "", ".md"),
        ("markdown", "python", ".md"),
        ("code", "python", ".py"),
        ("code", "py", ".py"),
        ("code", "typescript", ".ts"),
        ("code", "yml", ".yaml"),
        ("code", "c++", ".cpp"),
        ("code", "brainfuck", ".txt"),
        ("code", "", ".txt"),
        ("html", "", ".txt"),
    ],
)
def test_a_file_name_ends_in_the_extension_of_its_kind(kind, language, extension):
    assert filename_for("Kế hoạch", kind, language) == "Kế hoạch" + extension
