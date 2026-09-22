"""Wikilinks, backlinks, and the boundary between what the machine owns and what it must
leave alone."""

from my_agent_crew.memory.wiki_links import (
    CLOSE,
    OPEN,
    authored_body,
    backlinks_of,
    links_in,
    render_related,
    set_managed,
    split_managed,
)


def test_links_come_back_as_slugs_so_one_target_is_one_lookup():
    text = "Xem [[Hạn Eco]] và [[hạn eco]], rồi [[Sổ sách]]."
    assert links_in(text) == ["han-eco", "so-sach"]


def test_something_that_only_looks_like_a_link_is_not_one():
    assert links_in("[[chưa đóng và [mở đơn]") == []
    assert links_in("không có gì") == []


def test_a_body_with_no_block_is_all_the_authors():
    assert split_managed("  chỉ thân bài  ") == ("chỉ thân bài", "")


def test_the_authors_words_come_back_unchanged_after_a_rewrite():
    """The failure this prevents: a compile overwrites the one correction someone made by
    hand, and the vault becomes a thing nobody can fix."""
    written = "Dòng đầu.\n\nDòng hai, có [[so-sach]].\n"
    with_block = set_managed(written, render_related(["so-sach"], []))
    assert authored_body(with_block) == written.strip()

    again = set_managed(with_block, render_related(["so-sach", "han-eco"], ["khac"]))
    assert authored_body(again) == written.strip()
    # And the machine's part really was replaced, not appended twice.
    assert again.count(OPEN) == 1 and again.count(CLOSE) == 1
    assert "han-eco" in again and "khac" in again


def test_an_empty_block_leaves_no_heading_behind():
    """A page with nothing to relate to should look finished, not broken."""
    assert render_related([], []) == ""
    assert set_managed("thân bài", "") == "thân bài"


def test_a_page_that_had_a_block_and_now_relates_to_nothing_loses_it():
    body = set_managed("thân bài", render_related(["x"], []))
    assert set_managed(body, "") == "thân bài"


def test_backlinks_point_the_other_way():
    pages = {
        "han-eco": "Xem [[so-sach]].",
        "so-sach": "Không trỏ đi đâu.",
        "khac": "Cũng xem [[so-sach]] nữa.",
    }
    assert backlinks_of(pages) == {
        "han-eco": [],
        "so-sach": ["han-eco", "khac"],
        "khac": [],
    }


def test_a_link_to_a_page_that_does_not_exist_makes_no_backlink():
    # The lint reports the broken link; the graph must not grow a node for it.
    assert backlinks_of({"a": "Xem [[khong-co]]."}) == {"a": []}


def test_a_page_linking_to_itself_is_not_its_own_backlink():
    assert backlinks_of({"a": "Xem [[a]]."}) == {"a": []}


def test_the_generated_block_does_not_invent_a_mutual_link():
    """Counting the managed block as evidence would make every link mutual the moment it
    was rendered once, and the next compile would report a graph it had itself made up."""
    a_body = set_managed("Xem [[b]].", render_related(["b"], []))
    b_body = set_managed("Không trỏ đi đâu.", render_related([], ["a"]))
    assert backlinks_of({"a": a_body, "b": b_body}) == {"a": [], "b": ["a"]}
