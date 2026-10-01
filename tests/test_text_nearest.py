"""Where an edit that matched nothing was probably aimed: the closest passage, quoted with
its context, found at a bounded cost and never when two passages are about as close."""

from __future__ import annotations

import asyncio
import difflib
import re

from my_agent_crew.texts_canvas import ARTIFACT_EDIT_NO_MATCH
from my_agent_crew.tools import text_nearest
from my_agent_crew.tools.text_edit import EditNotFound
from my_agent_crew.tools.text_nearest import (
    MATCH_TOKENS,
    MISS_CHARS,
    MISS_LINES,
    explain_miss,
    nearest_region,
)

PROSE = "\n".join(
    f"Đoạn {n}: chiến dịch {word} cần {n * 3} người, ngân sách {n * 7} triệu, chốt ngày {n}/10."
    for n, word in enumerate(
        ["mùa thu", "biển xanh", "núi cao", "phố cổ", "đồng lúa", "sông dài", "rừng thông"], 1
    )
)
CLOSE_TO_LINE_4 = "Đoạn 4: chiến dịch phố cổ cần 12 người, ngân sách 30 triệu, chốt ngày 4/10."


def test_a_miss_names_the_closest_lines_and_quotes_them_verbatim():
    region = nearest_region(PROSE, CLOSE_TO_LINE_4)
    assert region is not None and (region.first, region.last) == (1, 7)
    assert region.text == PROSE


def test_the_miss_message_fences_the_region_after_the_plain_not_found():
    error = asyncio.run(explain_miss(PROSE, CLOSE_TO_LINE_4))
    assert isinstance(error, EditNotFound)
    head, rest = str(error).split("\n", 1)
    assert head == ARTIFACT_EDIT_NO_MATCH
    assert "dòng 1–7" in rest and rest.endswith(f"\n```\n{PROSE}\n```")


def test_nothing_alike_gives_no_region():
    assert nearest_region(PROSE, "hoàn toàn khác biệt, không một chữ nào trùng") is None
    assert str(asyncio.run(explain_miss(PROSE, "zzz qqq"))) == ARTIFACT_EDIT_NO_MATCH


def test_a_lone_passage_sharing_too_little_gives_no_region():
    text = "\n".join(
        [
            "Kế hoạch tháng mười",
            "Thứ hai họp nhóm lúc chín giờ sáng tại phòng lớn",
            "Ghi chú: laptop",
        ]
    )
    assert nearest_region(text, "Thứ hai nghỉ ở nhà vì trời mưa to cả buổi chiều") is None


def test_two_equally_close_places_give_no_region():
    text = "\n".join(["tiêu đề"] + ["- giá táo 10 nghìn"] * 2 + ["kết", "- giá táo 10 nghìn"])
    assert nearest_region(text, "- giá táo 12 nghìn") is None


def test_a_long_old_on_a_long_text_compares_at_most_three_windows(monkeypatch):
    lines = [f"dòng {n} có mã {n * 7919 % 100_003} và chữ lặp lại" for n in range(2400)]
    text = "\n".join(lines)
    old = "\n".join(lines[1200:1600]).replace("lặp lại", "lặp lai", 1)
    assert len(text) > 60_000 and len(old) > 12_000
    built = []

    class Counting(difflib.SequenceMatcher):
        def __init__(self, isjunk, a, b, **kwargs):
            built.append(max(len(a), len(b)))
            super().__init__(isjunk, a, b, **kwargs)

    monkeypatch.setattr(text_nearest, "SequenceMatcher", Counting)
    region = nearest_region(text, old)
    assert len(built) <= 3 and max(built) <= MATCH_TOKENS
    assert region is not None and region.first == 1201


def test_a_fence_line_repeated_everywhere_does_not_pull_the_region_away():
    blocks = [f"```\nhàm_{n}()\n```" for n in range(40)]
    blocks[23] = "```\ntính_lương(nhân_viên, tháng)\n```"
    lines = "\n".join(blocks).split("\n")
    region = nearest_region("\n".join(lines), "```\ntính_lương(nhân_viên, tháng_này)\n```")
    assert region is not None and (region.first, region.last) == (67, 75)
    assert region.text.split("\n") == lines[66:75]


def test_a_region_around_a_huge_line_stays_within_its_size():
    huge = "chữ " * 75_000
    text = "đầu\n" + huge + "ngân sách quý ba là 40 triệu" + huge + "\ncuối"
    region = nearest_region(text, "ngân sách quý ba là 45 triệu")
    assert region is not None and (region.first, region.last) == (1, 3)
    assert "ngân sách quý ba là 40 triệu" in region.text
    assert len(region.text) <= MISS_CHARS and region.text.startswith("đầu\n")


def test_a_long_run_of_matching_lines_is_cut_to_the_line_limit():
    lines = [f"mục {n}: số {n * 31 % 997}" for n in range(300)]
    old = "\n".join(lines[100:200]).replace("mục 150", "mục 15O")
    region = nearest_region("\n".join(lines), old)
    assert region is not None and region.first == 101
    shown = region.text.split("\n")
    assert len(shown) == MISS_LINES and region.last - region.first + 1 == MISS_LINES - 1
    assert shown[:-1] == lines[100 : 100 + MISS_LINES - 1]
    assert re.fullmatch(r"… \(\+\d+ dòng\)", shown[-1])


def test_an_old_too_long_to_search_gives_no_region():
    assert nearest_region(PROSE, "x" * 20_001 + PROSE) is None
