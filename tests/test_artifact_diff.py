"""What canvas results are built from: the tag that opens a write's result, the fence around
quoted canvas text, a long line shown around the part that matters, and the diff that shows
what a write changed without ever outgrowing its budget."""

from __future__ import annotations

import difflib
import re

import pytest

from my_agent_crew.artifacts import diff
from my_agent_crew.artifacts.diff import (
    DIFF_LINE_CHARS,
    DiffText,
    diff_text,
    excerpt,
    fenced,
    fenced_diff,
    middle_lines,
    render_diff,
)
from my_agent_crew.artifacts.tag import TAG_RE, artifact_tag
from my_agent_crew.texts_canvas import DIFF_HUNK, LINE_CUT_HEAD, LINE_CUT_TAIL, LINES_CUT

ID = "0123456789ab"
HEAD = re.escape(LINE_CUT_HEAD).replace(r"\{n\}", r"(\d+)")
TAIL = re.escape(LINE_CUT_TAIL).replace(r"\{n\}", r"(\d+)")


def _unwrap(shown: str) -> tuple[int, str, int]:
    """How many characters a shortened line left out before, what it kept, and how many it
    left out after."""
    match = re.fullmatch(f"(?:{HEAD})?(.*?)(?:{TAIL})?", shown, re.S)
    assert match is not None
    before, kept, after = match.groups()
    return int(before or 0), kept, int(after or 0)


def test_both_forms_of_the_tag_read_back_through_the_shared_pattern():
    assert TAG_RE.match(artifact_tag(ID, 7)).groups() == (ID, "7", None)
    assert TAG_RE.match(artifact_tag(ID, 7, unchanged=True)).groups() == (ID, "7", " unchanged")


def test_the_tag_only_counts_at_the_very_start_of_a_result():
    assert TAG_RE.search("Canvas «x» " + artifact_tag(ID, 1)) is None


@pytest.mark.parametrize("text", ["thường", "a ``` b", "````\nmã\n````", "`x`", "```"])
def test_a_fence_is_longer_than_any_backtick_run_inside(text):
    block = fenced(text, "md")
    fence = block.split("\n", 1)[0].removesuffix("md")
    assert set(fence) == {"`"} and len(fence) >= 3
    assert all(len(fence) > len(run) for run in re.findall(r"`+", text))
    assert block == f"{fence}md\n{text}\n{fence}"


def test_a_line_that_fits_is_kept_whole():
    assert excerpt("ngắn", 0, 4, 80) == "ngắn"


def test_a_long_line_is_shown_around_the_part_asked_for():
    line = "a" * 1000 + "ĐỔI" + "b" * 1000
    shown = excerpt(line, 1000, 1003, 120)
    before, kept, after = _unwrap(shown)
    assert len(shown) <= 120 and "ĐỔI" in kept
    assert line[before : len(line) - after] == kept
    assert abs(kept.index("ĐỔI") - (len(kept) - kept.index("ĐỔI") - 3)) <= 1


def test_a_part_wider_than_the_room_is_shown_from_its_start():
    line = "x" * 500 + "BẮT ĐẦU" + "y" * 5000
    before, kept, after = _unwrap(excerpt(line, 500, 3000, 200))
    assert before == 500 and kept.startswith("BẮT ĐẦU") and after > 0


def test_a_part_at_the_end_of_a_line_keeps_the_end():
    line = "x" * 5000 + "CUỐI"
    before, kept, after = _unwrap(excerpt(line, 5000, 5004, 100))
    assert kept.endswith("CUỐI") and after == 0 and before + len(kept) == len(line)


def test_removed_lines_take_at_most_half_and_what_was_written_always_shows():
    before = "\n".join(f"dòng cũ số {n} " + "chữ " * 20 for n in range(200))
    diff = render_diff(before, "dòng mới duy nhất", 1000)
    removed = [line for line in diff.split("\n") if line.startswith("- ")]
    assert "+ dòng mới duy nhất" in diff.split("\n")
    assert sum(len(line) + 1 for line in removed) <= 500
    assert LINES_CUT.format(n=200 - len(removed)) in diff.split("\n")
    assert len(diff) <= 1000


def test_a_changed_long_line_is_cut_around_the_change_on_both_sides():
    before = "x" * 5000 + " giá cũ " + "y" * 5000
    after = "x" * 5000 + " giá mới " + "y" * 5000
    removed, added = render_diff(before, after, 2000).split("\n")[1:]
    assert removed.startswith("- ") and "giá cũ" in removed
    assert added.startswith("+ ") and "giá mới" in added
    assert len(removed) <= DIFF_LINE_CHARS + 2 and len(added) <= DIFF_LINE_CHARS + 2


@pytest.mark.parametrize("budget", [200, 700, 3000])
def test_the_diff_never_outgrows_its_budget(budget):
    before = "\n".join(f"{n} " + "chữ" * (n % 50) * 9 for n in range(300))
    after = "\n".join(f"{n} sửa " + "từ" * (n % 70) * 7 for n in range(0, 300, 2))
    diff = render_diff(before, after, budget)
    assert 0 < len(diff) <= budget


def test_the_closing_count_always_fits_inside_the_budget():
    """Room for the count of lines left out is set aside before any line goes in."""
    after = "\n".join(["đầu"] + [f"mục {n:03}" for n in range(60)])
    for budget in range(20, 400):
        assert len(render_diff("đầu", after, budget)) <= budget, budget


def test_a_long_added_line_is_cut_to_the_room_left_rather_than_dropped():
    lines = render_diff("a", "a\n" + "z" * 4000, 200).split("\n")
    assert lines[0] == DIFF_HUNK.format(span="2") and len(lines) == 2
    before, kept, after = _unwrap(lines[1].removeprefix("+ "))
    assert before == 0 and kept == "z" * len(kept) and after == 4000 - len(kept)
    assert len("\n".join(lines)) <= 200


def test_hunk_headings_number_lines_as_split_on_newline_alone():
    """A form feed or a Unicode line separator stays inside its line, as the store keeps it."""
    before = "một\nhai\x0cvẫn hai\nba\N{LINE SEPARATOR}vẫn ba\nbốn"
    after = before.replace("bốn", "BỐN")
    assert render_diff(before, after, 500).split("\n") == [
        DIFF_HUNK.format(span="4"),
        "- bốn",
        "+ BỐN",
    ]


def test_inserted_and_removed_runs_are_headed_by_their_place_in_the_new_text():
    before = "a\nb\nc\nd"
    assert render_diff(before, "a\nb\nX\nY\nc\nd", 500).split("\n") == [
        DIFF_HUNK.format(span="3–4"),
        "+ X",
        "+ Y",
    ]
    assert render_diff(before, "a\nd", 500).split("\n") == [
        DIFF_HUNK.format(span="2"),
        "- b",
        "- c",
    ]
    assert render_diff(before, "a\nX\nb\nc\nD", 500).split("\n") == [
        DIFF_HUNK.format(span="2"),
        "+ X",
        DIFF_HUNK.format(span="5"),
        "- d",
        "+ D",
    ]


def test_no_difference_is_an_empty_diff():
    assert render_diff("giống\nhệt", "giống\nhệt", 500) == ""


def test_a_long_line_with_nothing_to_pair_is_cut_from_its_start():
    diff = render_diff("a", "a\n" + "z" * 4000, 2000)
    added = diff.split("\n")[1]
    before, kept, after = _unwrap(added.removeprefix("+ "))
    assert before == 0 and kept == "z" * len(kept) and after == 4000 - len(kept)
    assert _unwrap(LINE_CUT_TAIL.format(n=3)) == (0, "", 3)


def test_only_the_changed_middle_of_a_long_text_is_compared(monkeypatch):
    """Lines shared at either end are set aside first, so one changed row in a long table of
    identical rows costs nothing like comparing the whole table."""
    compared = []

    class Recording(difflib.SequenceMatcher):
        def __init__(self, isjunk, a, b, **kwargs):
            compared.append((len(a), len(b)))
            super().__init__(isjunk, a, b, **kwargs)

    monkeypatch.setattr(diff, "SequenceMatcher", Recording)
    rows = ["| --- | --- |"] * 15_000
    before, after = "\n".join([*rows, "| a |", *rows]), "\n".join([*rows, "| b |", *rows])
    assert render_diff(before, after, 500).split("\n") == [
        DIFF_HUNK.format(span="15001"),
        "- | a |",
        "+ | b |",
    ]
    assert compared == [(1, 1)]


@pytest.mark.parametrize("room", [40, 120, 500, 2000])
def test_a_fenced_diff_fits_its_room_whole(room):
    before = "\n".join(f"dòng {n}" for n in range(200))
    after = "\n".join(f"DÒNG {n}" for n in range(200))
    block = fenced_diff(before, after, room)
    assert len(block) <= room
    assert block.startswith("```diff\n") and block.endswith("\n```")


@pytest.mark.parametrize("room", range(60, 400, 7))
def test_a_diff_quoting_a_backtick_run_is_drawn_again_to_fit_a_longer_fence(room):
    before = "\n".join(f"`````{n}" for n in range(50))
    after = "\n".join(f"`````{n}!" for n in range(50))
    block = fenced_diff(before, after, room)
    assert len(block) <= room
    assert block.startswith("``````diff\n") and block.endswith("\n``````")


def test_a_room_too_small_for_any_line_still_ends_with_the_count_alone():
    block = fenced_diff("a\nb", "a\nc", 5)
    assert block == fenced(LINES_CUT.format(n=2), "diff")


def test_a_diff_that_shows_every_changed_line_in_full_is_whole():
    shown = diff_text("a\nb\nc", "a\nB\nc\nd", 500)
    assert shown == DiffText(render_diff("a\nb\nc", "a\nB\nc\nd", 500), whole=True)
    assert diff_text("giống", "giống", 500) == DiffText("", whole=True)


def test_a_diff_with_a_line_cut_around_its_change_is_not_whole():
    before, after = "x" * 5000 + " giá cũ", "x" * 5000 + " giá mới"
    shown = diff_text(before, after, 2000)
    assert shown.text == render_diff(before, after, 2000)
    assert re.search(HEAD, shown.text) and shown.whole is False


def test_a_diff_that_counts_removed_lines_instead_of_showing_them_is_not_whole():
    before = "\n".join(f"dòng cũ số {n} " + "chữ " * 20 for n in range(200))
    shown = diff_text(before, "dòng mới duy nhất", 1000)
    assert "+ dòng mới duy nhất" in shown.text.split("\n") and shown.whole is False


def test_a_diff_that_runs_out_of_room_for_later_changes_is_not_whole():
    before = "\n".join(f"dòng {n}" for n in range(100))
    after = "\n".join(f"DÒNG {n}" if n % 10 == 0 else f"dòng {n}" for n in range(100))
    shown = diff_text(before, after, 120)
    lines = shown.text.split("\n")
    assert lines[0] == DIFF_HUNK.format(span="1") and lines[1:3] == ["- dòng 0", "+ DÒNG 0"]
    assert lines[-1] == LINES_CUT.format(n=20 - _counted(shown.text))
    assert shown.whole is False
    assert diff_text(before, after, 3000).whole is True


def test_a_last_added_line_cut_to_the_room_left_is_not_whole():
    shown = diff_text("a", "a\n" + "z" * 4000, 200)
    assert shown.text.split("\n")[0] == DIFF_HUNK.format(span="2")
    assert shown.whole is False


def test_an_added_line_that_fits_only_once_cut_is_not_whole_even_when_it_ends_the_diff():
    """The cut line is counted as shown, so the count alone would call the diff whole."""
    shown = diff_text("a", "a\n" + "z" * 250, 200)
    assert len(shown.text.split("\n")) == 2 and shown.whole is False


def _counted(text: str) -> int:
    return sum(1 for line in text.split("\n") if line.startswith(("- ", "+ ")))


@pytest.mark.parametrize(
    ("before", "after", "middle"),
    [
        ("a\nb\nc", "a\nb\nc", 0),
        ("a\nb\nc", "a\nX\nc", 1),
        ("a\nb\nc", "a\nX\nY\nZ\nc", 3),
        ("a\nb\nc\nd\ne", "a\ne", 3),
        ("đầu\n" + "giữa\n" * 50 + "cuối", "ĐẦU\n" + "giữa\n" * 50 + "CUỐI", 52),
    ],
)
def test_the_changed_middle_counts_lines_between_the_shared_ends(before, after, middle):
    assert middle_lines(before, after) == middle
