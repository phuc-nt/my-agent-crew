"""The two soft guards of a crew browser: the hosts an agent was given, and the words in a
name that stop an action for a person."""

from __future__ import annotations

import unicodedata

import pytest

from my_agent_crew.browser.policy import (
    AskWords,
    host_allowed,
    host_of,
    plain,
    read_address,
    words,
)
from my_agent_crew.texts_browser import DEFAULT_ASK_WORDS


@pytest.mark.parametrize(
    "url, host",
    [
        ("https://shop.example/don-hang", "shop.example"),
        ("https://Shop.Example:8443/x?y=1#z", "shop.example"),
        ("https://shop.example./", "shop.example"),
        ("https://my_shop.example/", "my_shop.example"),
        ("http://203.0.113.9/x", "203.0.113.9"),
        ("https://[2001:db8::1]:8443/", "2001:db8::1"),
        ("https://bücher.example/", "xn--bcher-kva.example"),
        ("about:blank", ""),
        ("", ""),
        ("/orders", ""),
        ("https:///no-host", ""),
        ("https://[not-an-address/", ""),
        ("https://a..b.example/", ""),
        ("https://" + "a" * 64 + ".example/", ""),
        # A name with a number in it that does not end in one stays the name it is.
        ("http://123.example/", "123.example"),
        ("http://1e3/", "1e3"),
        ("http://0x1g/", "0x1g"),
        ("http://1_0/", "1_0"),
        ("http://shop.example.123a/", "shop.example.123a"),
    ],
)
def test_the_host_of_an_address_is_read_the_way_a_certificate_spells_it(url, host):
    assert host_of(url) == host


@pytest.mark.parametrize(
    "url, host",
    [
        ("http://2130706433/", "127.0.0.1"),
        ("http://0x7f000001/", "127.0.0.1"),
        ("http://0X7F000001/", "127.0.0.1"),
        ("http://017700000001/", "127.0.0.1"),
        ("http://0177.0.0.1/", "127.0.0.1"),
        ("http://127.000.000.001/", "127.0.0.1"),
        ("http://127.1/", "127.0.0.1"),
        ("http://0x7f.1/", "127.0.0.1"),
        ("http://127.0.0.0x1./", "127.0.0.1"),
        ("http://\uff11\uff12\uff17.0.0.1/", "127.0.0.1"),  # full-width digits fold into plain
        ("http://127\u30020\u30020\u30021/", "127.0.0.1"),  # and so does an ideographic stop
        ("http://0/", "0.0.0.0"),
        ("http://0x/", "0.0.0.0"),
        ("http://0300.0250.0.1/", "192.168.0.1"),
        ("http://0xa9fea9fe/", "169.254.169.254"),
        ("http://10.1/", "10.0.0.1"),
        ("http://1.2.3/", "1.2.0.3"),
        ("http://1.2.65535/", "1.2.255.255"),
        ("http://1.256/", "1.0.1.0"),  # only the last part is wider than a byte
        ("http://1.16777215/", "1.255.255.255"),
        ("http://4294967295/", "255.255.255.255"),
        # A leading zero is octal to a browser: this is not the private 10.0.0.1 it looks like.
        ("http://010.0.0.1/", "8.0.0.1"),
        ("http://0127.0.0.1/", "87.0.0.1"),
        ("http://134744072:8080/a?b=1#c", "8.8.8.8"),
    ],
)
def test_a_host_written_in_numbers_is_the_address_a_browser_makes_of_it(url, host):
    """Chromium reads every one of these so (the pinned one was asked). The browser is given
    the plain spelling, so what was judged is what is opened."""
    address = read_address(url)

    assert address.host == host and host_of(address.url) == host
    assert address.url.startswith(f"http://{host}") and read_address(address.url) == address
    assert address.url.endswith("/a?b=1#c") == url.endswith("/a?b=1#c")


@pytest.mark.parametrize(
    "host",
    [
        "1.2.3.4.5",
        "shop.123",
        "shop.example.0x10",
        "shop.example.010",
        "shop.example.09",
        "shop.0x",
        "x.0",
        "08",
        "09.1",
        "1.2.3.08",
        "256.1.1.1",
        "0x100.1.1.1",
        "1.1.1.256",
        # A part over 255 does not carry into the next, and a fifth part is not dropped.
        "1.256.1.1",
        "1.1.256.1",
        "1.2.3.4.0",
        "0.0.0.0.0",
        "1.2.0x10000",
        "1.16777216",
        "4294967296",
        "0x1ffffffff",
    ],
)
def test_a_host_that_ends_in_a_number_and_is_no_address_is_no_host(host):
    """A browser opens none of them, so none is a name a rule could be met by."""
    assert read_address(f"https://{host}/") is None and host_of(f"http://{host}:80/x") == ""


@pytest.mark.parametrize(
    "url",
    [
        # A browser takes a backslash for a slash: its host is evil.test in all three.
        "https://evil.test\\.shop.example/",
        "https://evil.test\\@shop.example/",
        "https://evil.test\\/shop.example/",
        "https://user:secret@shop.example/",
        "https://shop.example@evil.test/",
        "https://shop.example%2eevil.test/",
        "https://%73hop.example/",
        "https://shop.example /",
        " https://shop.example/",
        "https://shop\t.example/",
        "https://shop.example\n.evil.test/",
        "https://shop.example\uff0fevil.test/",  # a full-width slash folds into a real one
        "https://shop.example\uff20evil.test/",
        "https://shop.example\u200b.evil.test/",
        "https://shop.example,evil.test/",
        "https://shop.example<.evil.test/",
        "https://*.shop.example/",
        "https://shop.example:99999/",
        "https://[::1/",
        "https://[shop.example]/",
    ],
)
def test_an_address_a_browser_might_read_another_way_names_no_host(url):
    assert read_address(url) is None and host_of(url) == ""
    assert not host_allowed(host_of(url), ["shop.example", "*.shop.example", "evil.test"])


@pytest.mark.parametrize(
    "url, given",
    [
        ("https://shop.example/don-hang?id=1#top", "https://shop.example/don-hang?id=1#top"),
        ("HTTPS://Shop.Example:8443/A?b=C", "https://shop.example:8443/A?b=C"),
        ("https://shop.example.:/x", "https://shop.example./x"),
        ("https://bücher.example/sách", "https://xn--bcher-kva.example/sách"),
        ("https://straße.example/", "https://strasse.example/"),
        ("http://[2001:DB8::1]:8080/", "http://[2001:db8::1]:8080/"),
        ("https://shop.example/a\\b@c%2f", "https://shop.example/a\\b@c%2f"),
    ],
)
def test_the_browser_is_given_the_spelling_the_host_was_read_from(url, given):
    address = read_address(url)

    assert address.url == given
    assert host_of(given) == address.host and read_address(given) == address


@pytest.mark.parametrize(
    "host, patterns, allowed",
    [
        ("shop.example", ["shop.example"], True),
        ("www.shop.example", ["shop.example"], False),
        ("shop.example", ["*.shop.example"], True),
        ("www.shop.example", ["*.shop.example"], True),
        ("a.b.shop.example", ["*.shop.example"], True),
        ("notshop.example", ["*.shop.example"], False),
        ("notshop.example", ["shop.example"], False),
        ("shop.example.evil.test", ["*.shop.example", "shop.example"], False),
        ("example", ["*.shop.example"], False),
        ("other.test", ["shop.example", "*.other.test"], True),
        ("shop.example", [], False),
        ("", ["shop.example"], False),
        ("", ["*."], False),
    ],
)
def test_a_host_is_the_agents_own_only_as_its_list_names_it(host, patterns, allowed):
    assert host_allowed(host, patterns) is allowed


def test_a_host_read_from_an_address_is_matched_whatever_its_case_port_or_dot():
    given = ["*.shop.example"]

    assert host_allowed(host_of("https://WWW.Shop.Example.:8443/gio-hang"), given)
    assert not host_allowed(host_of("https://shop.example.evil.test/"), given)
    assert not host_allowed(host_of("https://evil.test/?next=https://shop.example/"), given)
    assert not host_allowed(host_of("https://shop.example@evil.test/"), given)


def test_words_are_letters_and_digits_in_a_row_in_lower_case():
    assert words("Đặt hàng — NGAY!") == ["đặt", "hàng", "ngay"]
    assert words("btn_pay-now2") == ["btn", "pay", "now2"]
    assert words("CheckOut PayNow") == ["check", "out", "pay", "now"]
    assert words("  \n ") == []


def test_a_name_spelled_with_separate_accent_marks_is_the_same_words():
    apart = unicodedata.normalize("NFD", "Thanh toán")

    assert apart != "Thanh toán" and words(apart) == ["thanh", "toán"]


@pytest.mark.parametrize(
    "unseen",
    [
        "\u00ad",  # a soft hyphen
        "\u061c",  # a mark of the direction a line is written in
        "\u180e",
        "\u200b",  # a zero-width space
        "\u200d",
        "\u200f",
        "\u202a",
        "\u202c",
        "\u2060",  # a word joiner
        "\u2064",
        "\u206f",
        "\ufe00",  # a variation selector
        "\ufe0f",
        "\ufeff",
        "\ufff0",
        "\U0001bca0",
        "\U0001d173",
        "\U000e0001",  # a tag character
        "\U000e0061",
        "\U000e0fff",
    ],
)
def test_what_a_browser_draws_nothing_for_parts_no_word(unseen):
    assert words(f"p{unseen}ay{unseen} n{unseen}{unseen}ow") == ["pay", "now"]
    assert words(unseen) == []


@pytest.mark.parametrize("blank", ["\u115f", "\u1160", "\u3164", "\uffa0"])
def test_a_letter_drawn_as_an_empty_place_parts_two_words(blank):
    assert words(f"pay{blank}now") == ["pay", "now"]
    assert words(f"p{blank}ay") == ["p", "ay"]


def test_a_letter_drawn_in_another_form_is_the_plain_letter():
    assert words("\uff50\uff41\uff59") == ["pay"]  # full width
    assert words("\uff23\uff48\uff45\uff43\uff4b\uff2f\uff55\uff54") == ["check", "out"]
    assert words("\U0001d429\U0001d41a\U0001d432") == ["pay"]  # mathematical bold
    assert words("\u24df\u24d0\u24e8") == ["pay"]  # circled
    assert words("con\ufb01rm") == ["confirm"]  # a ligature of f and i


def test_a_mark_that_makes_no_letter_with_the_one_under_it_is_not_read():
    # A dot under a `p` and a ring around an `a`: no such letters, so the eye reads `pay`.
    assert words("p\u0323a\u20ddy") == ["pay"]
    # A mark that does make a letter stays in it, in whichever order the marks were typed.
    assert words("\u0110a\u0323\u0306t ha\u0300ng") == ["đặt", "hàng"]
    assert words("mu\u0300a") == ["mùa"]


def test_a_letter_of_another_alphabet_is_not_the_one_it_looks_like():
    cyrillic = "\u0440\u0430\u0443"  # draws as `pay`

    assert words(cyrillic) == [cyrillic]
    assert AskWords(["pay"]).find(cyrillic) == ""
    assert AskWords(["pay"]).find("\u1e55ay") == ""  # a `p` with an accent is another letter


def test_a_word_without_accents_has_no_marks_and_a_plain_d():
    assert plain("đặt") == "dat"
    assert plain("hủy") == "huy"
    assert plain("pay") == "pay"


ASK = AskWords(DEFAULT_ASK_WORDS)


@pytest.mark.parametrize(
    "name, pattern",
    [
        ("Đặt hàng", "đặt hàng"),
        ("ĐẶT HÀNG NGAY", "đặt hàng"),
        ("Dat hang", "đặt hàng"),
        ("Đặt hang", "đặt hàng"),
        ("Tiến hành thanh toán (3 món)", "thanh toán"),
        ("Thanh toan", "thanh toán"),
        ("Mua ngay", "mua"),
        ("Xoá khỏi giỏ", "xoá"),
        ("Xóa", "xóa"),
        ("Xoa", "xoá"),
        ("Huỷ đơn #1234", "huỷ đơn"),
        ("Huy don", "huỷ đơn"),
        ("Gửi", "gửi"),
        ("Gui", "gửi"),
        ("Đăng xuất", "đăng xuất"),
        ("Pay now", "pay"),
        ("PayNow", "pay"),
        ("btn_pay", "pay"),
        ("Proceed to Checkout", "checkout"),
        ("Check out", "check out"),
        ("Place your order", "order"),
        ("Log out", "log out"),
        ("Sign   out", "sign out"),
        ("Delete account", "delete"),
        ("P\u200bay now", "pay"),
        ("\uff30\uff41\uff59", "pay"),
        ("Thanh\u00ad toa\u0301n", "thanh toán"),
        ("Trả tiền", "trả tiền"),
        ("Tra tien", "trả tiền"),
        ("Nạp tiền vào ví", "nạp tiền"),
        ("Rút tiền", "rút tiền"),
        ("Đặt cọc 500k", "đặt cọc"),
        ("Đặt chỗ", "đặt chỗ"),
        ("Đặt vé ngay", "đặt vé"),
        ("Dat phong", "đặt phòng"),
        ("Đăng ký gói năm", "đăng ký"),
        ("Chấp nhận tất cả", "chấp nhận"),
        ("Nộp hồ sơ", "nộp"),
        ("Subscribe", "subscribe"),
        ("Accept all", "accept"),
        ("Book now", "book now"),
        ("Withdraw", "withdraw"),
        ("Deposit", "deposit"),
        ("Donate $5", "donate"),
        ("Place bid", "bid"),
    ],
)
def test_a_name_holding_an_ask_word_is_found_by_the_pattern_it_matches(name, pattern):
    assert ASK.find(name) == pattern


@pytest.mark.parametrize(
    "name",
    [
        "Mùa thu",  # another word: accents that are not the pattern's
        "Múa lân",
        "Đạt hạng nhất",
        "Thành toàn",
        "Gùi",
        "Đơn hàng của tôi",
        "Giỏ hàng",
        "Tiếp theo",
        "Hàng đặt trước",  # the words, not in the pattern's order
        "Đặt lại hàng",  # the words, not in a row
        "Orders",  # a longer word is not the word
        "Payment methods",
        "Repay",
        "Postcard",
        "Senders",
        "Sign in",
        "Check in / out of stock",
        "Book a table",  # the word alone is no pattern
        "Bookmarks",
        "Bidding",
        "Acceptable",
        "Subscribers",
        "Đăng nhập",
        "Đặt lại mật khẩu",
        "Tiền mặt",
        "",
        "→",
    ],
)
def test_a_name_that_only_looks_like_an_ask_word_is_not_found(name):
    assert ASK.find(name) == ""


def test_an_accented_word_in_a_name_is_not_matched_by_a_pattern_written_without_accents():
    typed_plain = AskWords(["mua", "dat hang"])

    assert typed_plain.find("mua") == "mua"
    assert typed_plain.find("mùa") == ""
    assert typed_plain.find("Đặt hàng") == ""
    assert typed_plain.find("dat hang") == "dat hang"


def test_the_first_pattern_of_the_list_is_the_one_named():
    assert AskWords(["ngay", "mua"]).find("Mua ngay") == "ngay"
    assert AskWords(["mua ngay", "mua"]).find("Mua ngay") == "mua ngay"


def test_a_pattern_longer_than_the_name_is_not_found():
    assert AskWords(["đặt hàng ngay bây giờ"]).find("Đặt hàng") == ""


def test_no_patterns_and_patterns_without_a_word_ask_for_nothing():
    assert not AskWords(())
    assert not AskWords(["", "  ", "—", "_"])
    assert AskWords(()).find("Thanh toán") == ""
    assert AskWords(["—"]).find("—") == ""
    assert AskWords(["—", "mua"]).find("Tiếp theo") == ""
    assert AskWords(DEFAULT_ASK_WORDS)
