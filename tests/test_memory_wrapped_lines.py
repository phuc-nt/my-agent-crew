"""A bullet of `MEMORY.md` wrapped by hand over two lines is one fact to the rewrite gate:
joining it onto one line removes nothing, while dropping or changing its second half still
does."""

from __future__ import annotations

from my_agent_crew.memory import fact_dates
from my_agent_crew.memory.wrapped_lines import logical_lines

WRAPPED = (
    "## Phạm vi\n"
    "- Tách khỏi Pong ngày 2026-09-23: Pong giờ chỉ giữ Google Workspace; mọi việc\n"
    "  sổ cái, nhắc hạn, giá vàng, giấy tờ về đây.\n"
    "- Sếp thích trà.\n"
)
JOINED = (
    "## Phạm vi\n"
    "- Tách khỏi Pong ngày 2026-09-23: Pong giờ chỉ giữ Google Workspace; mọi việc sổ cái,"
    " nhắc hạn, giá vàng, giấy tờ về đây. (2026-11-02)\n"
    "- Sếp thích trà.\n"
)


def test_a_wrapped_bullet_is_read_as_one_line():
    assert logical_lines(WRAPPED) == [
        "## Phạm vi",
        "- Tách khỏi Pong ngày 2026-09-23: Pong giờ chỉ giữ Google Workspace; mọi việc"
        " sổ cái, nhắc hạn, giá vàng, giấy tờ về đây.",
        "- Sếp thích trà.",
    ]


def test_joining_a_wrapped_bullet_removes_nothing_either_way():
    assert fact_dates.removed_lines(WRAPPED, JOINED) == []
    assert fact_dates.removed_lines(JOINED, WRAPPED) == []


def test_dropping_the_second_half_of_a_wrapped_bullet_is_still_a_removal():
    cut = WRAPPED.split("\n  sổ cái")[0] + "\n"
    [removed, tea] = fact_dates.removed_lines(WRAPPED, cut)
    assert removed.endswith("giấy tờ về đây.") and tea == "- Sếp thích trà."


def test_only_an_indented_line_after_a_bullet_continues_it():
    text = "- Một.\nCâu riêng.\n  - Bullet con.\n\n  thụt sau dòng trống\n# Đề\n  thụt sau đề"
    assert logical_lines(text) == [
        "- Một.",
        "Câu riêng.",
        "- Bullet con.",
        "thụt sau dòng trống",
        "# Đề",
        "thụt sau đề",
    ]
