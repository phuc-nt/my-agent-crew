"""Markdown a model writes, read on a phone: a morning brief's table of books arrived as
rows of pipes under a `|---|---|` line, framed by `---` rules and `*(…)*` asterisks."""

from __future__ import annotations

from my_agent_crew.channels.telegram_plain_text import plain_text


def test_a_table_becomes_one_line_per_row_without_its_divider():
    table = (
        "📚 Sách đang đọc\n\n"
        "| Tên | Tác giả |\n"
        "|---|---|\n"
        "| Những người khốn khổ | Victor Hugo |\n"
        "| *(+ 2 cuốn nữa)* | |"
    )
    assert plain_text(table) == (
        "📚 Sách đang đọc\n\nTên · Tác giả\nNhững người khốn khổ · Victor Hugo\n(+ 2 cuốn nữa)"
    )


def test_an_aligned_divider_is_dropped_too():
    assert plain_text("| Ngày | HRV |\n|:---|---:|\n| 22/9 | 57 |") == "Ngày · HRV\n22/9 · 57"


def test_rules_become_a_single_blank_line():
    assert plain_text("Lịch trống\n\n---\n\n\n\nEmail: 19 tin") == "Lịch trống\n\nEmail: 19 tin"


def test_italics_lose_their_asterisks_but_arithmetic_keeps_them():
    assert plain_text("*ghi chú* và **đậm**, 2*3*4 = 24") == "ghi chú và đậm, 2*3*4 = 24"


def test_prose_with_a_lone_pipe_is_left_alone():
    assert plain_text("RHR 57 | HRV 51") == "RHR 57 | HRV 51"
