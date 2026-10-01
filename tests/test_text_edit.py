"""How an agent's edit finds its place in a canvas: exactly, or with curly quotes and odd
spaces read as plain ones, never ambiguously and never past the kind's cap."""

from __future__ import annotations

import pytest

from my_agent_crew.texts_canvas import (
    ARTIFACT_EDIT_AMBIGUOUS,
    ARTIFACT_EDIT_EMPTY_OLD,
    ARTIFACT_EDIT_NO_MATCH,
    ARTIFACT_EDIT_TOO_LARGE,
)
from my_agent_crew.tools import text_nearest
from my_agent_crew.tools.registry import ToolError
from my_agent_crew.tools.text_edit import EditNotFound, apply_edit, normalize_for_match

NBSP, NARROW, FIGURE = "\N{NO-BREAK SPACE}", "\N{NARROW NO-BREAK SPACE}", "\N{FIGURE SPACE}"
LEFT_1, RIGHT_1 = "\N{LEFT SINGLE QUOTATION MARK}", "\N{RIGHT SINGLE QUOTATION MARK}"
LEFT_2, RIGHT_2 = "\N{LEFT DOUBLE QUOTATION MARK}", "\N{RIGHT DOUBLE QUOTATION MARK}"
PROSE = "\n".join(
    f"Đoạn {n}: chiến dịch {word} cần {n * 3} người, ngân sách {n * 7} triệu, chốt ngày {n}/10."
    for n, word in enumerate(
        ["mùa thu", "biển xanh", "núi cao", "phố cổ", "đồng lúa", "sông dài", "rừng thông"], 1
    )
)
CLOSE_TO_LINE_4 = "Đoạn 4: chiến dịch phố cổ cần 12 người, ngân sách 30 triệu, chốt ngày 4/10."


def test_an_exact_match_is_replaced_where_it_stands():
    assert apply_edit("một hai ba", "hai", "HAI") == ("một HAI ba", 1)


def test_curly_quotes_and_odd_spaces_match_their_plain_forms():
    text = f"Anh ấy nói {LEFT_2}xin{NBSP}chào{RIGHT_2} rồi đi{NARROW}về."
    new = f"nói {LEFT_2}tạm biệt{RIGHT_2} rồi"
    edited, count = apply_edit(text, 'nói "xin chào" rồi', new)
    assert count == 1 and edited == f"Anh ấy nói {LEFT_2}tạm biệt{RIGHT_2} rồi đi{NARROW}về."


def test_a_curly_old_matches_plain_text_too():
    assert apply_edit("it's done", f"it{RIGHT_1}s", "it is") == ("it is done", 1)


def test_an_exact_match_wins_over_loose_ones():
    """The loose reading only runs when the exact one finds nothing."""
    text = f"a 'x' b {LEFT_1}x{RIGHT_1}"
    assert apply_edit(text, "'x'", "y") == (f"a y b {LEFT_1}x{RIGHT_1}", 1)


def test_a_loose_match_in_several_places_is_refused_with_the_count():
    text = ", ".join([f"{LEFT_2}A{RIGHT_2}"] * 3)
    with pytest.raises(ToolError) as caught:
        apply_edit(text, '"A"', "B")
    assert str(caught.value) == ARTIFACT_EDIT_AMBIGUOUS.format(count=3)
    assert apply_edit(text, '"A"', "B", replace_all=True) == ("B, B, B", 3)


def test_an_exact_match_in_several_places_is_refused_unless_all_are_asked_for():
    with pytest.raises(ToolError) as caught:
        apply_edit("ab ab", "ab", "x")
    assert str(caught.value) == ARTIFACT_EDIT_AMBIGUOUS.format(count=2)
    assert apply_edit("ab ab", "ab", "x", replace_all=True) == ("x x", 2)


def test_an_empty_old_is_refused():
    with pytest.raises(ToolError) as caught:
        apply_edit("chữ", "", "thêm")
    assert str(caught.value) == ARTIFACT_EDIT_EMPTY_OLD
    assert not isinstance(caught.value, EditNotFound)


def test_no_match_raises_a_bare_not_found_without_searching(monkeypatch):
    """Edits run inside the store's lock, so finding the closest passage waits until later."""
    monkeypatch.setattr(text_nearest, "nearest_region", _forbidden)
    monkeypatch.setattr(text_nearest, "SequenceMatcher", _forbidden)
    with pytest.raises(EditNotFound) as caught:
        apply_edit(PROSE, CLOSE_TO_LINE_4, "x")
    assert str(caught.value) == ARTIFACT_EDIT_NO_MATCH


def _forbidden(*_args, **_kwargs):
    raise AssertionError("the nearest-region search ran inside apply_edit")


def test_the_cap_counts_the_bytes_of_what_was_really_matched():
    """A loose match replaces the canvas's own characters, a two-byte NBSP among them."""
    assert apply_edit(f"a{NBSP}b", "a b", "a b", cap=3) == ("a b", 1)
    with pytest.raises(ToolError) as caught:
        apply_edit(f"a{NBSP}b", "a b", "a  b", cap=3)
    assert str(caught.value) == ARTIFACT_EDIT_TOO_LARGE.format(size=4, cap=3)


def test_a_result_exactly_at_the_cap_is_kept_and_one_byte_over_is_not():
    text = "ab " * 10
    assert apply_edit(text, "ab", "ạ", replace_all=True, cap=40)[0] == "ạ " * 10
    with pytest.raises(ToolError) as caught:
        apply_edit(text, "ab", "ạ", replace_all=True, cap=39)
    assert str(caught.value) == ARTIFACT_EDIT_TOO_LARGE.format(size=40, cap=39)


def test_an_oversized_replace_all_is_refused_before_it_is_built():
    text = "a" * 100_000
    with pytest.raises(ToolError) as caught:
        apply_edit(text, "a", "b" * 100_000, replace_all=True, cap=512 * 1024)
    assert str(caught.value) == ARTIFACT_EDIT_TOO_LARGE.format(size=10**10, cap=512 * 1024)


@pytest.mark.parametrize(
    "text", [NBSP + NARROW + FIGURE, LEFT_1 + RIGHT_1 + LEFT_2 + RIGHT_2, PROSE]
)
def test_normalizing_keeps_every_character_in_its_place(text):
    assert len(normalize_for_match(text)) == len(text)
