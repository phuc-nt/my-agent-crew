"""Finding a thought in a note: what counts as one entry, and which one comes first."""

from __future__ import annotations

from my_agent_crew.memory.search import MAX_CHARS, Entry, normalize, search, split_entries

NOTE = """# Mua sắm

- Jimny 5 cửa,
  ngân sách 1.5 tỷ
- Bút Wancher còn chờ

# Đọc

Đang đọc Sụp đổ của Jared Diamond.
Chưa xong chương ba.
"""


def test_a_bullet_keeps_the_lines_that_belong_to_it():
    """The budget sits on the second line; matching line by line would lose the pair."""
    entries = split_entries(NOTE)
    assert [e.heading for e in entries] == ["Mua sắm", "Mua sắm", "Đọc"]
    assert entries[0].text == "- Jimny 5 cửa,\n  ngân sách 1.5 tỷ"
    assert entries[2].text.endswith("Chưa xong chương ba.")


def test_numbered_items_are_entries_too():
    entries = split_entries("1. đầu tiên\n2. thứ hai\n   kèm chi tiết")
    assert [e.text for e in entries] == ["1. đầu tiên", "2. thứ hai\n   kèm chi tiết"]


def test_a_paragraph_without_any_heading_is_still_an_entry():
    entries = split_entries("chỉ một đoạn\nhai dòng")
    assert entries == [Entry(heading="", text="chỉ một đoạn\nhai dòng", order=0)]


def test_accents_are_dropped_on_both_sides():
    assert normalize("Sức Khoẻ") == normalize("suc khoe")


def test_a_query_typed_without_accents_finds_the_entry():
    hits = search([("2026-09-19.md", NOTE)], "ngan sach jimny", limit=5)
    assert hits[0].source == "2026-09-19.md › Mua sắm"
    assert "1.5 tỷ" in hits[0].text


def test_entries_with_every_word_push_out_the_partial_ones():
    hits = search([("note.md", NOTE)], "jimny ngân", limit=5)
    assert len(hits) == 1 and "Jimny" in hits[0].text


def test_partial_matches_are_still_worth_showing_when_nothing_is_complete():
    """Half an answer beats none; only a full match makes a partial one noise."""
    hits = search([("note.md", NOTE)], "jimny wancher", limit=5)
    assert len(hits) == 2 and all(h.found == 1 for h in hits)


def test_the_vietnamese_d_is_not_an_accent():
    assert normalize("Đang đọc") == "dang doc"


def test_a_word_found_whole_outranks_the_same_word_inside_another():
    """Without accents `doc` is inside `docs`; the entry that has the word wins."""
    files = [("a.md", "- xem docs của thư viện"), ("b.md", "- đang đọc sách mới")]
    hits = search(files, "doc", limit=5)
    assert hits[0].source == "b.md"


def test_a_very_short_word_has_to_be_found_whole():
    """Without accents `ô` is an `o`, which sits inside almost every Vietnamese entry."""
    files = [("a.md", "- uống trà nóng"), ("b.md", "- ô tô mới")]
    assert [h.source for h in search(files, "ô", limit=5)] == ["b.md"]


def test_the_caller_order_breaks_a_tie():
    files = [("user/tra.md", "- Sếp thích trà."), ("2026-09-19.md", "- Sếp thích trà.")]
    assert [h.source for h in search(files, "trà", limit=5)] == ["user/tra.md", "2026-09-19.md"]


def test_a_long_entry_is_cut_and_folded_onto_one_line():
    hits = search([("note.md", "- jimny " + "x" * 400)], "jimny", limit=5)
    assert len(hits[0].text) == MAX_CHARS and hits[0].text.endswith("…")


def test_an_empty_query_finds_nothing():
    assert search([("note.md", NOTE)], "   ", limit=5) == []


def test_the_limit_is_respected():
    text = "\n".join(f"- trà số {n}" for n in range(20))
    assert len(search([("note.md", text)], "trà", limit=4)) == 4
