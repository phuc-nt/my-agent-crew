"""The two soft guards of a crew browser: the hosts an agent was given, and the words in a
name that stop an action for a person."""

from __future__ import annotations

import unicodedata

import pytest

from my_agent_crew.browser.policy import AskWords, host_allowed, host_of, plain, words
from my_agent_crew.texts_browser import DEFAULT_ASK_WORDS


@pytest.mark.parametrize(
    "url, host",
    [
        ("https://shop.example/don-hang", "shop.example"),
        ("https://Shop.Example:8443/x?y=1#z", "shop.example"),
        ("https://shop.example./", "shop.example"),
        ("https://user:secret@shop.example/", "shop.example"),
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
    ],
)
def test_the_host_of_an_address_is_read_the_way_a_certificate_spells_it(url, host):
    assert host_of(url) == host


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
