"""Reading the outline Playwright draws of a page back into refs, names and ask words, and
what of it the model is given."""

from __future__ import annotations

import unicodedata

import pytest

from my_agent_crew.browser.policy import AskWords
from my_agent_crew.browser.snapshot import (
    Line,
    Node,
    Shown,
    address,
    read,
    same_name,
    traits,
    with_mark,
)
from my_agent_crew.browser.snapshot_view import LIST, NEW, QUERY, TREE, added, view
from my_agent_crew.texts_browser import DEFAULT_ASK_WORDS

ASK = AskWords(DEFAULT_ASK_WORDS)
# As the browser drew a shop page: names with quotes, a colon and a bracket, a form.
SHOP = """\
- generic [active] [ref=e1]:
  - heading "Đơn hàng" [level=1] [ref=e2]
  - link "Đơn của tôi" [ref=e3] [cursor=pointer]:
    - /url: /orders
  - button "Đặt hàng" [ref=e4]
  - button "Xoá \\"Sách\\" khỏi giỏ" [ref=e5]: x
  - button "Dòng 1 Dòng 2" [ref=e6]
  - button "Nhiều khoảng trắng" [ref=e7]
  - button "Có [ref=e99] trong tên" [ref=e8]: "y"
  - 'button "Tên: có hai chấm" [ref=e9]'
  - button [ref=e10]
  - generic [ref=e11]:
    - generic [ref=e12]:
      - text: Mật khẩu
      - textbox "Mật khẩu" [ref=e13]
    - generic [ref=e16]:
      - text: Tên
      - textbox "Tên" [ref=e17]: Phúc
    - combobox "Cách giao" [ref=e18]:
      - option "Nhanh" [selected]
      - option "Thường"
    - checkbox "Đồng ý" [ref=e19]
    - text: Đồng ý
    - button "Thanh toán" [ref=e20]
  - paragraph [ref=e21]: Văn bản thường, không có ref.
  - img "ảnh" [ref=e22]"""


def nodes(outline: str, ask: AskWords = ASK) -> dict[str, Node]:
    return dict(read(outline, ask).nodes)


def test_every_element_drawn_with_a_ref_is_read_with_its_role_and_name():
    table = nodes(SHOP)

    assert list(table) == [f"e{n}" for n in (*range(1, 14), *range(16, 23))]
    assert (table["e2"].role, table["e2"].name) == ("heading", "Đơn hàng")
    assert (table["e3"].role, table["e3"].name) == ("link", "Đơn của tôi")
    assert table["e5"].name == 'Xoá "Sách" khỏi giỏ'
    assert table["e9"] == Node("e9", "button", "Tên: có hai chấm")
    assert table["e10"] == Node("e10", "button", "")
    assert (table["e17"].role, table["e17"].name) == ("textbox", "Tên")
    assert table["e21"] == Node("e21", "paragraph", "")


def test_a_ref_written_inside_a_name_or_a_value_is_no_ref():
    table = nodes(SHOP + '\n  - paragraph [ref=e23]: xem [ref=e98] ở trên\n  - text: "[ref=e97]"')

    assert table["e8"].name == "Có [ref=e99] trong tên"
    assert not {"e99", "e98", "e97"} & set(table)


def test_an_element_carries_the_ask_word_of_its_own_name():
    table = nodes(SHOP)

    assert table["e4"].word == "đặt hàng"
    assert table["e5"].word == "xoá"
    assert table["e19"].word == "đồng ý"
    assert table["e20"].word == "thanh toán"
    assert [table[r].word for r in ("e2", "e3", "e6", "e13", "e17", "e18", "e21", "e22")] == [
        ""
    ] * 8


def test_a_box_carries_the_first_ask_word_of_what_it_holds():
    table = nodes(SHOP)

    assert table["e11"].word == "đồng ý"  # the form: its checkbox comes before its button
    assert table["e1"].word == "đặt hàng"  # the page: the first button on it
    assert table["e12"].word == table["e16"].word == ""


def test_a_clickable_box_asks_for_the_words_written_in_or_under_it():
    table = nodes(
        "- generic [ref=e1]:\n"
        "  - generic [ref=e2] [cursor=pointer]: Mua ngay\n"
        "  - generic [ref=e3] [cursor=pointer]:\n"
        "    - generic [ref=e4]:\n"
        "      - text: Thanh toán\n"
        "  - generic [ref=e5] [cursor=pointer]:\n"
        '    - img "Xoá"\n'
        "  - generic [ref=e6] [cursor=pointer]: Xem thêm"
    )

    assert [table[f"e{n}"].word for n in range(1, 7)] == [
        "mua",
        "mua",
        *["thanh toán"] * 2,
        "xoá",
        "",
    ]


def test_a_word_does_not_reach_what_stands_beside_or_after_it():
    table = nodes(
        "- generic [ref=e1]:\n"
        "  - generic [ref=e2]:\n"
        '    - button "Thanh toán" [ref=e3]\n'
        '    - button "Quay lại" [ref=e4]\n'
        '  - button "Tiếp" [ref=e5]\n'
        '- button "Trang sau" [ref=e6]'
    )

    assert [table[f"e{n}"].word for n in range(1, 7)] == ["thanh toán"] * 3 + [""] * 3


# As the browser drew them: a button or a link that holds elements has no name of its own, and
# what it says stands on the lines under it.
INSIDE = """\
- generic [active] [ref=e1]:
  - button [ref=e2]:
    - img "thùng rác" [ref=e3]
    - text: Xoá tài khoản
  - link [ref=e5] [cursor=pointer]:
    - /url: /hit?a1
    - heading "Gói Pro" [level=3] [ref=e6]
    - paragraph [ref=e7]: 199.000đ mỗi tháng
    - text: Mua ngay
  - button [ref=e8]:
    - paragraph [ref=e9]: Tài khoản của bạn
    - paragraph [ref=e10]: Xoá vĩnh viễn
  - button [ref=e11]:
    - img "biểu tượng" [ref=e12]
    - text: Gửi tiền
  - generic [ref=e14] [cursor=pointer]:
    - text: Xoá hẳn
    - paragraph [ref=e15]: Không hoàn tác được
    - img "x" [ref=e16]
  - button "Xem" [ref=e17]:
    - img "mắt" [ref=e18]"""


def test_what_stands_inside_a_control_asks_for_the_word_the_control_holds():
    """A click on the picture in a button presses the button."""
    table = nodes(INSIDE)

    assert {ref: table[ref].word for ref in table if ref not in ("e1", "e17", "e18")} == {
        **dict.fromkeys(("e2", "e3"), "xoá"),
        **dict.fromkeys(("e5", "e6", "e7"), "mua"),
        **dict.fromkeys(("e8", "e9", "e10"), "xoá"),
        **dict.fromkeys(("e11", "e12"), "gửi"),
        **dict.fromkeys(("e14", "e15", "e16"), "xoá"),
    }
    assert (table["e17"].word, table["e18"].word) == ("", "")


PRESSED = "button link menuitem menuitemcheckbox menuitemradio tab option checkbox radio switch"
HOLDING = "generic listitem row cell paragraph heading group form dialog list region textbox"


@pytest.mark.parametrize("role", [*PRESSED.split(), "treeitem"])
def test_every_kind_of_control_a_click_sets_off_gives_its_word_to_what_it_holds(role):
    table = nodes(f'- {role} [ref=e1]:\n  - img "hình" [ref=e2]\n  - text: Xoá')

    assert (table["e1"].word, table["e2"].word) == ("xoá", "xoá")


@pytest.mark.parametrize("role", [*HOLDING.split(), "combobox"])
def test_what_only_holds_things_gives_them_no_word(role):
    table = nodes(f'- {role} [ref=e1]:\n  - img "hình" [ref=e2]\n  - text: Xoá')

    assert (table["e1"].word, table["e2"].word) == ("xoá", "")


def test_a_word_goes_down_only_inside_what_a_click_sets_off():
    """A row, a list item, a form or a box no pointer shows over sets nothing off by itself:
    what stands beside a word in one of them is still its own thing."""
    table = nodes(
        "- generic [ref=e1]:\n"
        "  - text: Thanh toán\n"
        "  - paragraph [ref=e2]: Bằng thẻ\n"
        "- row [ref=e3]:\n"
        '  - cell "Đơn 12" [ref=e4]\n'
        "  - cell [ref=e5]:\n"
        '    - button "Xem" [ref=e6]\n'
        "  - cell [ref=e7]:\n"
        '    - button "Xoá" [ref=e8]\n'
        '- form "Thanh toán" [ref=e9]:\n'
        '  - textbox "Ghi chú" [ref=e10]\n'
        '  - button "Tiếp" [ref=e11]\n'
        "- listitem [ref=e12]:\n"
        "  - text: Xoá\n"
        '  - link "Trang chủ" [ref=e13] [cursor=pointer]:\n'
        "    - /url: /x\n"
        '- textbox "Thư" [ref=e14]:\n'
        "  - paragraph [ref=e15]: Gửi anh Nam\n"
        "  - paragraph [ref=e16]: Hẹn gặp"
    )

    assert {ref: node.word for ref, node in table.items() if node.word} == {
        "e1": "thanh toán",
        "e3": "xoá",
        "e7": "xoá",
        "e8": "xoá",
        "e9": "thanh toán",
        "e12": "xoá",
        "e14": "gửi",
        "e15": "gửi",
    }


def test_a_control_inside_another_keeps_its_words_and_takes_those_of_the_one_around_it():
    table = nodes(
        "- generic [ref=e1] [cursor=pointer]:\n"
        '  - heading "Áo sơ mi" [level=3] [ref=e2]\n'
        '  - button "Mua" [ref=e3]\n'
        "- link [ref=e4] [cursor=pointer]:\n"
        "  - /url: /goi\n"
        "  - text: Thanh toán\n"
        '  - button "Xem" [ref=e5]:\n'
        '    - img "mắt" [ref=e6]\n'
        '  - button "Xoá" [ref=e7]:\n'
        '    - img "thùng" [ref=e8]'
    )

    # The card is clicked for what it holds, its title is not: the word is the button's own.
    assert [table[f"e{n}"].word for n in (1, 2, 3)] == ["mua", "", "mua"]
    # A button in a link presses the link too, and what is in that button with it.
    assert [table[f"e{n}"].word for n in (4, 5, 6)] == ["thanh toán"] * 3
    assert [table[f"e{n}"].word for n in (7, 8)] == ["xoá", "xoá"]


def test_the_address_of_a_link_asks_for_nothing():
    table = nodes('- link "Tiếp" [ref=e1] [cursor=pointer]:\n  - /url: /order/confirm?pay=1')

    assert table["e1"] == Node("e1", "link", "Tiếp")


def test_a_key_in_single_quotes_is_read_with_its_own_quotes_put_back():
    table = nodes(
        "- 'link \"A: b\" [ref=e2] [cursor=pointer]':\n"
        "  - /url: /a\n"
        "- 'button \"It''s: here\" [ref=e3]': x\n"
        "- 'button \"Gửi: ngay\" [ref=e4]'"
    )

    assert table["e2"] == Node("e2", "link", "A: b")
    assert table["e3"] == Node("e3", "button", "It's: here")
    assert table["e4"] == Node("e4", "button", "Gửi: ngay", "gửi")


@pytest.mark.parametrize(
    "line",
    [
        "- button /Mua.*/ [ref=e7]",  # a name drawn as a pattern
        '- button "Mua [ref=e7]',  # a name never closed
        '- \'button "Mua" [ref=e7]',  # a key never closed
        '- button "Mua" [ref=e7] [ref=e8]',  # two refs
        '- button "Mua\\q" [ref=e7]',  # a name that is no JSON
        '- button "Mua" [ref=e7] rồi gì đó',  # something after the key that is no value
        '- button "Mua" [ref=e7]:x',
        'button "Mua" [ref=e7]',  # not an item of the outline
        '- button "Mua" [a]b] [ref=e7]',
    ],
)
def test_a_line_not_drawn_the_way_an_element_is_gives_nothing_to_act_on(line):
    table = nodes(f'- generic [ref=e1]:\n  {line}\n  - button "Sau" [ref=e9]')

    assert set(table) == {"e1", "e9"}
    assert table["e1"].word == "mua"  # what it says still counts for the box it is in
    assert table["e9"].word == ""


def test_a_ref_drawn_twice_finds_nothing():
    table = nodes('- button "Một" [ref=e1]\n- button "Hai" [ref=e2]\n- button "Ba" [ref=e1]')

    assert set(table) == {"e2"}


def test_a_value_in_quotes_is_read_and_one_with_odd_escapes_is_kept_as_drawn():
    snapshot = read(
        '- textbox "Tên" [ref=e1]: "Có: chấm \\"x\\""\n- paragraph [ref=e2]: "a\\x1fb: c"', ASK
    )

    assert [line.text for line in snapshot.lines] == ['Tên Có: chấm "x"', "a\\x1fb: c"]


def test_with_no_ask_words_nothing_carries_one_and_an_empty_outline_reads_as_nothing():
    assert {node.word for node in nodes(SHOP, AskWords(())).values()} == {""}
    assert read("", ASK).lines == () and read("\n  \n", ASK).lines == ()


def test_names_are_the_same_whatever_their_spacing_and_case():
    assert same_name("Đặt  hàng\n", " đặt HÀNG")
    assert same_name("", "  ")
    assert not same_name("Đặt hàng", "Đặt hàng ngay")
    assert not same_name("Dat hang", "Đặt hàng")


def test_the_address_of_a_page_is_without_what_follows_the_hash():
    assert address("https://shop.example/gio?a=1#thanh-toan") == "https://shop.example/gio?a=1"
    assert address("https://shop.example/") == "https://shop.example/"


def test_an_outline_that_fits_is_given_whole():
    seen = view(read(SHOP, ASK), 8000)

    assert (seen.text, seen.kind, seen.shown, seen.total) == (SHOP, TREE, 26, 26)


def test_an_outline_that_does_not_fit_is_cut_down_to_what_can_be_acted_on():
    seen = view(read(SHOP, ASK), len(SHOP))  # one character short: each line ends in one

    assert seen.kind == LIST and seen.shown == seen.total == 17
    assert seen.text.splitlines() == [
        '- heading "Đơn hàng" [level=1] [ref=e2]',
        '- link "Đơn của tôi" [ref=e3] [cursor=pointer]:',
        "  - /url: /orders",
        '- button "Đặt hàng" [ref=e4]',
        '- button "Xoá \\"Sách\\" khỏi giỏ" [ref=e5]: x',
        '- button "Dòng 1 Dòng 2" [ref=e6]',
        '- button "Nhiều khoảng trắng" [ref=e7]',
        '- button "Có [ref=e99] trong tên" [ref=e8]: "y"',
        "- 'button \"Tên: có hai chấm\" [ref=e9]'",
        "- button [ref=e10]",
        '- textbox "Mật khẩu" [ref=e13]',
        '- textbox "Tên" [ref=e17]: Phúc',
        '- combobox "Cách giao" [ref=e18]:',
        '  - option "Nhanh" [selected]',
        '  - option "Thường"',
        '- checkbox "Đồng ý" [ref=e19]',
        '- button "Thanh toán" [ref=e20]',
    ]


def test_the_list_is_given_on_request_and_holds_clickable_boxes_too():
    outline = (
        "- generic [ref=e1]:\n  - generic [ref=e2] [cursor=pointer]: Thẻ sản phẩm\n  - text: giá"
    )
    seen = view(read(outline, ASK), 8000, listed=True)

    assert (seen.text, seen.kind) == ("- generic [ref=e2] [cursor=pointer]: Thẻ sản phẩm", LIST)


def test_what_has_no_ref_cannot_be_acted_on_and_is_not_listed_nor_what_stands_under_it():
    outline = (
        '- button "Ẩn"\n- link "Ẩn":\n  - /url: /an\n- combobox "Ẩn":\n  - option "Một"\n'
        '- generic [cursor=pointer]: Thẻ\n- button "Hiện" [ref=e1]'
    )

    assert view(read(outline, ASK), 8000, listed=True).text == '- button "Hiện" [ref=e1]'


def test_a_search_for_nothing_but_spaces_is_no_search():
    assert view(read(SHOP, ASK), 8000, query="  \n").kind == TREE


def test_a_view_over_its_budget_ends_on_a_whole_line_and_says_how_many_there_were():
    snapshot = read(SHOP, ASK)
    first, second = snapshot.lines[1].drawn, snapshot.lines[2].drawn
    budget = len(first) + 1 + len(second) + 1

    assert view(snapshot, budget, listed=True).text == f"{first}\n{second}"
    cut = view(snapshot, budget - 1, listed=True)
    assert (cut.text, cut.shown, cut.total) == (first, 1, 17)
    assert view(snapshot, 3, listed=True).text == ""


def test_a_search_gives_the_lines_that_hold_it_under_the_lines_they_stand_under():
    seen = view(read(SHOP, ASK), 8000, query="  thanh   TOÁN ")

    assert seen.kind == QUERY and seen.shown == seen.total == 3
    assert seen.text == (
        '- generic [active] [ref=e1]:\n  - generic [ref=e11]:\n    - button "Thanh toán" [ref=e20]'
    )


def test_a_search_looks_in_values_and_addresses_and_in_either_spelling_of_an_accent():
    snapshot = read(SHOP, ASK)

    assert "[ref=e17]: Phúc" in view(snapshot, 8000, query="phúc").text
    assert view(snapshot, 8000, query="/orders").text.splitlines()[1:] == [
        '  - link "Đơn của tôi" [ref=e3] [cursor=pointer]:',
        "    - /url: /orders",
    ]
    assert "[ref=e17]" in view(snapshot, 8000, query=unicodedata.normalize("NFD", "Phúc")).text
    assert view(snapshot, 8000, query="không có trên trang").text == ""
    assert view(snapshot, 8000, query="không có trên trang").total == 0


def test_a_search_over_its_budget_is_cut_at_a_whole_line_too():
    seen = view(read(SHOP, ASK), 60, query="mật khẩu")

    assert seen.text == "- generic [active] [ref=e1]:\n  - generic [ref=e11]:"
    assert (seen.shown, seen.total) == (2, 5)


A = "https://shop.test/gio"
CART = """\
- generic [ref=e1]:
  - heading "Giỏ hàng" [level=1] [ref=e2]
  - link "Giỏ hàng (1)" [ref=e3] [cursor=pointer]:
    - /url: /gio
  - list [ref=e4]:
    - listitem [ref=e5]:
      - text: Áo
      - button "Xoá" [ref=e6]
    - listitem [ref=e7]:
      - text: Quần
      - button "Xoá" [ref=e8]
  - textbox "Ghi chú" [ref=e9]: cũ
  - button "Thêm" [ref=e10]"""
# After a click on "Thêm": a row put first, the count in the link, a note, a message.
CART_AFTER = """\
- generic [ref=e1]:
  - heading "Giỏ hàng" [level=1] [ref=e2]
  - link "Giỏ hàng (2)" [ref=e11] [cursor=pointer]:
    - /url: /gio
  - list [ref=e4]:
    - listitem [ref=e12]:
      - text: Áo khoác
      - button "Xoá" [ref=e13]
    - listitem [ref=e5]:
      - text: Áo
      - button "Xoá" [ref=e6]
    - listitem [ref=e7]:
      - text: Quần
      - button "Xoá" [ref=e8]
  - textbox "Ghi chú" [ref=e9]: mới
  - button "Thêm" [active] [ref=e10]
  - alert [ref=e14]: Đã thêm áo khoác"""


def shown(outline: str, url: str = A) -> Shown:
    snapshot = read(outline, ASK)
    return Shown(url, snapshot.nodes, traits(snapshot))


def came(before: str, after: str) -> set[str]:
    return set(added(shown(before), A, read(after, ASK)))


def test_what_came_or_changed_what_it_says_since_the_last_look_is_new():
    """Of three buttons alike, the one that came is the one whose ref was not there."""
    assert came(CART, CART_AFTER) == {"e11", "e12", "e13", "e9", "e14"}
    assert came(CART, CART) == set()
    assert came(CART_AFTER, CART) == {"e3", "e9"}  # what left is told by nothing


def test_a_page_drawn_again_is_paired_by_role_and_text_in_the_order_drawn():
    """Every ref is another, so of the three buttons alike the last drawn is the one more."""
    again = CART_AFTER.replace("[ref=e", "[ref=f1e")

    assert came(CART, CART.replace("[ref=e", "[ref=f1e")) == set()
    assert came(CART, again) == {"f1e11", "f1e7", "f1e8", "f1e9", "f1e14"}


def test_a_ref_that_now_finds_another_element_is_new_and_one_that_left_pairs_with_no_other():
    before = '- button "A" [ref=e1]\n- button "B" [ref=e2]'
    after = '- link "A" [ref=e1]\n- button "C" [ref=e2]\n- button "A" [ref=e3]'

    assert came(before, after) == {"e1", "e2"}
    # A ref drawn twice finds nothing, so it is nothing that could have come.
    assert came(before, before + '\n- button "Z" [ref=e5]\n- button "Z" [ref=e5]') == set()


def test_nothing_is_new_at_a_first_look_at_another_address_or_where_nothing_stayed():
    after = read(CART_AFTER, ASK)

    assert added(None, A, after) == frozenset()
    assert added(shown(CART, "https://shop.test/khac"), A, after) == frozenset()
    assert added(shown(CART), A, after) != frozenset()
    assert came('- button "A" [ref=e1]', '- button "B" [ref=e1]\n- link "C" [ref=e2]') == set()
    # The box a page is drawn in says nothing: with all else another, the page is another.
    box = "- generic [ref=e1]:\n  - list [ref=e2]:\n"
    step = box + '    - button "A" [ref=e3]'
    assert came(step, box + '    - button "B" [ref=e4]\n    - link "C" [ref=e5]') == set()
    assert came(step, box + '    - button "A" [ref=e3]\n    - link "C" [ref=e5]') == {"e5"}
    # What was kept without what its elements said has nothing to pair with.
    assert added(Shown(A, read(CART, ASK).nodes), A, after) == frozenset()


def test_the_mark_is_the_last_attribute_of_a_line_and_the_line_still_reads_as_its_element():
    snapshot = read(SHOP, ASK)
    lines = {line.ref: line for line in snapshot.lines if line.ref}

    assert with_mark(lines["e4"], NEW) == '- button "Đặt hàng" [ref=e4] [new]'
    assert with_mark(lines["e3"], NEW) == '- link "Đơn của tôi" [ref=e3] [cursor=pointer] [new]:'
    assert with_mark(lines["e5"], NEW) == '- button "Xoá \\"Sách\\" khỏi giỏ" [ref=e5] [new]: x'
    assert with_mark(lines["e8"], NEW) == '- button "Có [ref=e99] trong tên" [ref=e8] [new]: "y"'
    assert with_mark(lines["e9"], NEW) == "- 'button \"Tên: có hai chấm\" [ref=e9] [new]'"
    assert with_mark(lines["e10"], NEW) == "- button [ref=e10] [new]"
    quoted = read("- 'button \"It''s: a\" [ref=e1]': v", ASK).lines[0]
    assert with_mark(quoted, NEW) == "- 'button \"It''s: a\" [ref=e1] [new]': v"
    every = "\n".join(
        " " * line.indent + (with_mark(line, NEW) if line.ref else line.drawn)
        for line in snapshot.lines
    )
    assert every.count(NEW) == len(lines) and dict(read(every, ASK).nodes) == dict(snapshot.nodes)
    # A line that is no element has no place for a mark.
    loose = Line(0, '- "chỉ có tên"', "", "", "", "", -1, False)
    assert with_mark(loose, NEW) == loose.drawn


def test_a_new_element_is_marked_in_whichever_view_gives_its_line():
    snapshot = read(SHOP, ASK)
    fresh = {"e4", "e9", "e17", "e21"}
    whole = view(snapshot, 8000, fresh=fresh)
    listed = view(snapshot, 8000, listed=True, fresh=fresh)
    found = view(snapshot, 8000, query="phúc", fresh=fresh)

    assert [line.strip() for line in whole.text.splitlines() if NEW in line] == [
        '- button "Đặt hàng" [ref=e4] [new]',
        "- 'button \"Tên: có hai chấm\" [ref=e9] [new]'",
        '- textbox "Tên" [ref=e17] [new]: Phúc',
        "- paragraph [ref=e21] [new]: Văn bản thường, không có ref.",
    ]
    assert (whole.kind, whole.new, whole.text.replace(f" {NEW}", "")) == (TREE, 4, SHOP)
    # A paragraph is not something to act on: the list leaves it out, mark and all.
    assert (listed.kind, listed.new, listed.text.count(NEW)) == (LIST, 3, 3)
    assert '- textbox "Tên" [ref=e17] [new]: Phúc' in listed.text.splitlines()
    assert (found.kind, found.new) == (QUERY, 1)
    assert found.text.splitlines()[-1] == '      - textbox "Tên" [ref=e17] [new]: Phúc'
    assert view(snapshot, 8000).new == 0 and NEW not in view(snapshot, 8000).text
    # What a list holds under an element is marked as the element is.
    menu = '- listbox "Màu" [ref=e1]:\n  - option "Đỏ" [ref=e2]\n  - option "Xanh" [ref=e3]'
    under = view(read(menu, ASK), 8000, listed=True, fresh={"e3"})
    assert (under.text, under.new) == (menu + " [new]", 1)


def test_a_mark_takes_room_and_only_the_marks_given_are_counted():
    snapshot = read(SHOP, ASK)
    fits = len(SHOP) + 1  # each line ends in one character more
    first, second = snapshot.lines[1].drawn, snapshot.lines[2].drawn
    budget = len(first) + 1 + len(second) + 1 + 2 * (len(NEW) + 1)
    fresh = {"e2", "e3", "e4"}

    assert view(snapshot, fits).kind == TREE
    assert view(snapshot, fits, fresh={"e4"}).kind == LIST
    assert view(snapshot, fits + len(NEW) + 1, fresh={"e4"}).kind == TREE
    two = view(snapshot, budget, listed=True, fresh=fresh)
    assert (two.shown, two.new, two.total) == (2, 2, 17)
    one = view(snapshot, budget - 1, listed=True, fresh=fresh)
    assert (one.shown, one.new) == (1, 1)
