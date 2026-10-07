"""How what an agent holds is told to the agent that hands it work (`agents/abilities.py`):
a line for each kind of thing, a set of names against the reader's own where that is the
shorter way to say it, and nothing at all for a kind the agent has none of."""

from __future__ import annotations

from dataclasses import replace

import pytest

from my_agent_crew import texts
from my_agent_crew.agents.abilities import (
    DESCRIPTION_CHARS,
    DOWN,
    READ_ONLY,
    READ_WRITE,
    SIGNED_OUT,
    Abilities,
    Service,
    ability_lines,
    told_against,
)
from my_agent_crew.agents.profile import default_profile
from my_agent_crew.agents.roster import crew_roster_section
from my_agent_crew.config import Settings

MINE = ("read", "write", "shell", "memory")


@pytest.mark.parametrize(
    ("theirs", "said"),
    [
        (MINE, "như của bạn"),
        ((*MINE, "glob"), "như của bạn, thêm: glob"),
        (("read", "write", "shell"), "như của bạn, không có: memory"),
        (("read", "write", "shell", "glob"), "như của bạn, thêm: glob; không có: memory"),
        # Four names differ where there are four to list: the list itself is shorter.
        (("read", "write", "glob", "grep"), "read, write, glob, grep"),
        (("read",), "read"),
        (("glob", "grep"), "glob, grep"),
        ((), ""),
    ],
)
def test_names_are_told_against_the_readers_own_only_when_that_is_shorter(theirs, said):
    assert told_against(theirs, MINE) == said


def test_names_are_listed_whole_when_there_is_no_reader_to_compare_with():
    assert told_against(MINE, None) == "read, write, shell, memory"
    # A reader that holds nothing is still a reader: nothing of theirs is "like yours".
    assert told_against(("read",), ()) == "read"
    assert told_against((), ()) == ""


def test_the_half_way_mark_itself_is_still_told_against_the_reader():
    # Two names differ, four to list: exactly half.
    theirs = ("read", "write", "glob", "grep")
    assert told_against(theirs, ("read", "write")) == "như của bạn, thêm: glob, grep"
    assert told_against(theirs, ("read", "write", "x")) == "read, write, glob, grep"


FULL = Abilities(
    tools=("read", "glob"),
    skills=(("cite", "Dẫn nguồn"), ("gws", "Lịch và thư Google")),
    services=(Service("notion", READ_WRITE, "Sổ ghi chú"), Service("tracker", READ_ONLY)),
    jobs=("Bản tin sáng", "Tổng kết tuần"),
    model="small",
    escalation="big",
)


def test_each_kind_of_thing_an_agent_holds_gets_its_own_line_in_one_order():
    assert ability_lines(FULL) == [
        "  · Dịch vụ ngoài (MCP): notion (đọc và ghi) — Sổ ghi chú; tracker (chỉ đọc)",
        "  · Kỹ năng: cite (Dẫn nguồn), gws (Lịch và thư Google)",
        "  · Việc tự chạy theo lịch: Bản tin sáng, Tổng kết tuần",
        "  · Công cụ: read, glob",
        "  · Mô hình: small; khi bí thì tự chuyển sang big",
    ]


def test_a_kind_an_agent_has_none_of_is_not_mentioned():
    assert ability_lines(Abilities()) == []
    assert ability_lines(Abilities(jobs=("Bản tin sáng",))) == [
        "  · Việc tự chạy theo lịch: Bản tin sáng"
    ]
    assert ability_lines(replace(FULL, services=(), jobs=(), escalation="")) == [
        "  · Kỹ năng: cite (Dẫn nguồn), gws (Lịch và thư Google)",
        "  · Công cụ: read, glob",
        "  · Mô hình: small",
    ]
    # A model to move to says nothing of an agent whose own model is not known.
    assert ability_lines(Abilities(escalation="big")) == []


def test_a_server_is_told_with_how_far_the_agent_reaches_it_now():
    def said(standing: str) -> str:
        [line] = ability_lines(Abilities(services=(Service("notion", standing),)))
        return line

    assert said(READ_WRITE) == "  · Dịch vụ ngoài (MCP): notion (đọc và ghi)"
    assert said(READ_ONLY) == "  · Dịch vụ ngoài (MCP): notion (chỉ đọc)"
    assert said(SIGNED_OUT) == f"  · Dịch vụ ngoài (MCP): notion ({texts.CREW_SERVICE_SIGNED_OUT})"
    assert said(DOWN) == f"  · Dịch vụ ngoài (MCP): notion ({texts.CREW_SERVICE_DOWN})"
    assert "đăng nhập" in texts.CREW_SERVICE_SIGNED_OUT
    assert "chưa kết nối" in texts.CREW_SERVICE_DOWN


def test_a_skill_the_reader_holds_too_is_only_named():
    mine = Abilities(tools=("read", "glob"), skills=(("cite", "Dẫn nguồn"),))
    lines = ability_lines(replace(FULL, services=(), jobs=()), mine)
    assert lines[0] == "  · Kỹ năng: như của bạn, thêm: gws (Lịch và thư Google)"
    assert lines[1] == "  · Công cụ: như của bạn"

    plain = Abilities(skills=(("cite", "Dẫn nguồn"), ("gws", ""), ("pdf", "Đọc PDF")))
    assert ability_lines(plain, Abilities(skills=(("cite", ""), ("a", ""), ("b", "")))) == [
        "  · Kỹ năng: cite, gws, pdf (Đọc PDF)"
    ]
    # One the reader holds and the agent does not is the reader's own: named, never described.
    more = Abilities(skills=(("cite", "Dẫn nguồn"), ("gws", ""), ("pdf", ""), ("git", "Dùng git")))
    assert ability_lines(plain, more) == ["  · Kỹ năng: như của bạn, không có: git"]


def test_a_long_description_is_cut_to_one_item_of_a_line():
    wordy = "Tra  sách\nvà đánh giá " + "rất dài " * 30
    [line] = ability_lines(Abilities(skills=(("goodreads", wordy),)))
    described = line.removeprefix("  · Kỹ năng: goodreads (").removesuffix(")")
    assert described.startswith("Tra sách và đánh giá rất dài") and described.endswith("…")
    assert len(described) <= DESCRIPTION_CHARS

    exact = "x" * DESCRIPTION_CHARS
    [line] = ability_lines(Abilities(services=(Service("notion", READ_ONLY, exact),)))
    assert line.endswith(f"— {exact}")
    [line] = ability_lines(Abilities(services=(Service("notion", READ_ONLY, exact + "y"),)))
    assert line.endswith("— " + "x" * (DESCRIPTION_CHARS - 1) + "…")


def _three(settings: Settings):
    master = default_profile(settings)
    coder = replace(master, id="coder", name="Coder", description="viết mã")
    pong = replace(master, id="pong", name="Pong")
    return master, {"default": master, "coder": coder, "pong": pong}


def test_what_an_agent_holds_goes_under_its_own_line_of_the_roster(settings: Settings):
    master, peers = _three(settings)
    crew = {
        "default": Abilities(tools=("read", "write")),
        "coder": Abilities(tools=("read", "write", "glob", "grep")),
        "pong": Abilities(tools=("read", "write"), jobs=("Bản tin sáng",)),
    }
    _, body = crew_roster_section(master, peers, lambda: crew)

    assert body.splitlines()[-7:] == [
        "- coder — Coder (assistant): viết mã",
        "  · Công cụ: như của bạn, thêm: glob, grep",
        f"- pong — Pong (assistant): {texts.CREW_ROSTER_NO_DESCRIPTION}",
        "  · Việc tự chạy theo lịch: Bản tin sáng",
        "  · Công cụ: như của bạn",
        "",
        texts.CREW_ROSTER_ABILITIES_NOTE,
    ]

    # One agent with something to tell is enough for the note, wherever it stands in the list.
    _, body = crew_roster_section(master, peers, lambda: {"coder": crew["coder"]})
    assert body.splitlines()[-5:] == [
        "- coder — Coder (assistant): viết mã",
        "  · Công cụ: read, write, glob, grep",
        f"- pong — Pong (assistant): {texts.CREW_ROSTER_NO_DESCRIPTION}",
        "",
        texts.CREW_ROSTER_ABILITIES_NOTE,
    ]


def test_a_roster_with_nothing_read_from_the_crew_is_the_owners_lines_alone(settings: Settings):
    master, peers = _three(settings)
    plain = crew_roster_section(master, peers)[1]
    assert plain.splitlines()[-2:] == [
        "- coder — Coder (assistant): viết mã",
        f"- pong — Pong (assistant): {texts.CREW_ROSTER_NO_DESCRIPTION}",
    ]
    # An agent the crew says nothing of, or holds nothing, adds no line and no note on lines.
    assert crew_roster_section(master, peers, dict)[1] == plain
    assert crew_roster_section(master, peers, lambda: {"coder": Abilities()})[1] == plain


def test_the_crew_is_not_asked_when_there_is_nobody_to_list(settings: Settings):
    master, peers = _three(settings)
    asked: list[int] = []
    assert crew_roster_section(peers["coder"], peers, lambda: asked.append(1) or {}) is None
    assert asked == []


def test_the_note_says_whose_word_the_lines_are_and_that_they_outrank_what_was_said():
    note = texts.CREW_ROSTER_ABILITIES_NOTE
    assert "hệ thống đọc từ đội đang chạy" in note
    assert "điều bạn từng nói trong cuộc trò chuyện này" in note
    assert "đừng trả lời là không làm được" in note
