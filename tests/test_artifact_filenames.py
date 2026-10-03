"""The name a canvas is saved under when it is downloaded: its title in any script, less what
a file system refuses, and the extension of its kind, followed by `.txt` for a page or a picture
a browser would run when the file is opened. A raster picture takes its extension from its bytes."""

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
        ("code", "css", ".css"),
        ("code", "html", ".html.txt"),
        ("code", "brainfuck", ".txt"),
        ("code", "", ".txt"),
        ("html", "", ".html.txt"),
        ("html", "python", ".html.txt"),
        ("svg", "", ".svg.txt"),
        ("mermaid", "", ".mmd"),
        ("mermaid", "html", ".mmd"),
    ],
)
def test_a_file_name_ends_in_the_extension_of_its_kind(kind, language, extension):
    assert filename_for("Kế hoạch", kind, language) == "Kế hoạch" + extension


@pytest.mark.parametrize(
    ("data", "extension"),
    [
        (b"\x89PNG\r\n\x1a\n" + bytes(8), ".png"),
        (b"\xff\xd8\xff\xe0\x00\x10JFIF", ".jpg"),
        (b"GIF89a" + bytes(8), ".gif"),
        (b"RIFF\x1a\x00\x00\x00WEBPVP8 ", ".webp"),
        (b"<svg onload='alert(1)'/>", ".bin"),
        (b"", ".bin"),
        (None, ".bin"),
    ],
)
def test_a_picture_takes_the_extension_its_bytes_give_and_bin_when_they_give_none(data, extension):
    assert filename_for("Kế hoạch", "image", data=data) == "Kế hoạch" + extension


def test_the_bytes_of_a_canvas_never_change_the_name_of_a_text_kind():
    png = b"\x89PNG\r\n\x1a\n"
    assert filename_for("a", "html", data=png) == "a.html.txt"
    assert filename_for("a", "markdown", data=png) == "a.md"
