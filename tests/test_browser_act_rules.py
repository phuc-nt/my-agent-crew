"""What an action on a page is judged by before a browser is asked anything. No browser
here: the arguments of a call, a key, a field's own description, a name."""

from __future__ import annotations

import pytest

from my_agent_crew import texts_browser as t
from my_agent_crew.browser import act as a
from my_agent_crew.browser.policy import AskWords
from my_agent_crew.browser.snapshot import Node
from my_agent_crew.texts import WORKSPACE_ESCAPE
from my_agent_crew.tools.registry import ToolError

ASK = AskWords(("đặt hàng", "xoá", "pay"))


def refusal(call, *args) -> str:
    with pytest.raises(ToolError) as error:
        call(*args)
    return str(error.value)


def asked(tmp_path, **args) -> a.Asked:
    return a.read({"ref": "e5", "name": "Tìm", **args}, tmp_path)


def test_every_kind_is_read_with_what_it_needs_and_nothing_it_does_not(tmp_path):
    (tmp_path / "don.pdf").write_text("x")
    stray = {"text": "chữ", "key": "Enter", "value": "Đỏ", "path": "don.pdf"}

    made = {kind: asked(tmp_path, kind=kind, **stray) for kind in a.KINDS}

    assert set(made) == {"click", "type", "fill", "press", "select", "hover", "scroll", "upload"}
    assert made["click"] == a.Asked("click", "e5", "Tìm")
    assert made["hover"] == a.Asked("hover", "e5", "Tìm")
    assert made["scroll"] == a.Asked("scroll", "e5", "Tìm")
    assert made["type"] == a.Asked("type", "e5", "Tìm", text="chữ")
    assert made["fill"] == a.Asked("fill", "e5", "Tìm", text="chữ")
    assert made["press"] == a.Asked("press", "e5", "Tìm", key="Enter")
    assert made["select"] == a.Asked("select", "e5", "Tìm", value="Đỏ")
    assert made["upload"] == a.Asked("upload", "e5", "Tìm", file=tmp_path.resolve() / "don.pdf")


def test_a_kind_that_is_none_and_a_need_that_is_missing_are_said_by_name(tmp_path):
    kinds = ", ".join(a.KINDS)

    assert refusal(asked, tmp_path) == t.ACT_KIND.format(kind="", kinds=kinds)
    assert refusal(lambda: asked(tmp_path, kind="drag\n" + "x" * 60)) == t.ACT_KIND.format(
        kind="drag " + "x" * 35, kinds=kinds
    )
    assert refusal(lambda: asked(tmp_path, kind=["click"])) == t.ACT_KIND.format(
        kind="", kinds=kinds
    )
    for kind, what in a.NEEDS.items():
        assert refusal(lambda k=kind: asked(tmp_path, kind=k)) == t.ACT_NEEDS.format(
            kind=kind, what=what
        )
    for kind in a.KINDS:  # the ref is asked for first, whatever else is missing
        assert refusal(lambda k=kind: a.read({"kind": k, "ref": " "}, tmp_path)) == (
            t.ACT_NEEDS.format(kind=kind, what="ref")
        )
    for empty in ("  ", 7, None):
        assert refusal(lambda v=empty: asked(tmp_path, kind="select", value=v)) == (
            t.ACT_NEEDS.format(kind="select", what="value")
        )


def test_text_is_taken_as_written_and_only_fill_may_write_nothing(tmp_path):
    spaced = asked(tmp_path, kind="type", text="  hai chữ ")
    lines = asked(tmp_path, kind="fill", text="một\nhai\r\n")

    assert (spaced.text, lines.text) == ("  hai chữ ", "một\nhai\r\n")
    assert asked(tmp_path, kind="fill", text="").text == ""  # which empties the field
    assert refusal(lambda: asked(tmp_path, kind="type", text="")) == (
        t.ACT_NEEDS.format(kind="type", what="text")
    )
    for none in (None, 12, ["x"]):
        for kind in ("type", "fill"):
            assert refusal(lambda k=kind, v=none: asked(tmp_path, kind=k, text=v)) == (
                t.ACT_NEEDS.format(kind=kind, what="text")
            )
    # A line break typed is Enter pressed, which is another kind with rules of its own.
    for text in ("một\nhai", "một\rhai"):
        assert refusal(lambda v=text: asked(tmp_path, kind="type", text=v)) == t.ACT_NEWLINE
    assert asked(tmp_path, kind="click", name="  Đặt   hàng ").name == "Đặt   hàng"
    assert a.read({"kind": "click", "ref": "e5"}, tmp_path).name == ""  # an element with none


@pytest.mark.parametrize(
    ("given", "pressed"),
    [
        ("Enter", "Enter"),
        ("enter", "Enter"),
        ("ARROWDOWN", "ArrowDown"),
        ("pageup", "PageUp"),
        ("Space", "Space"),
        ("Shift+Tab", "Shift+Tab"),
        ("shift+tab", "Shift+Tab"),
        ("SHIFT+enter", "Shift+Enter"),
        ("a", "a"),
        ("A", "A"),
        ("7", "7"),
        ("/", "/"),
        ("+", "+"),
        ("Shift+a", "Shift+a"),
        ("shift+9", "Shift+9"),
    ],
)
def test_a_key_is_one_of_a_few_or_one_character_with_shift_at_most(given, pressed):
    assert a.key_of(given) == pressed


@pytest.mark.parametrize(
    "given",
    [
        "",
        "Control+a",
        "Meta+q",
        "Alt+F4",
        "Control+Enter",
        "Shift+Control+a",
        "Control+Shift+Tab",
        "F5",
        "ab",
        "Enter Enter",
        "Enter+Enter",
        "Shift+",
        "Shift+/",  # another character: type it as itself
        "Shift++",
        "é",
        "\x7f",
        "Insert",
    ],
)
def test_a_chord_or_a_key_off_the_list_is_refused(given):
    assert refusal(a.key_of, given) == t.ACT_KEY.format(key=given, keys=", ".join(a.KEYS))


def test_a_key_refused_is_told_on_one_line_and_short(tmp_path):
    long = "Control+\n" + "x" * 80

    assert refusal(lambda: asked(tmp_path, kind="press", key=long)) == t.ACT_KEY.format(
        key="Control+ " + "x" * 31, keys=", ".join(a.KEYS)
    )
    assert asked(tmp_path, kind="press", key=" shift+enter ").key == "Shift+Enter"
    assert "Enter, Tab, Escape" in t.ACT_KEY.format(key="x", keys=", ".join(a.KEYS))


def test_enter_sends_a_form_with_shift_or_without():
    assert [a.sends(key) for key in ("Enter", "Shift+Enter", "Tab", "Shift+Tab", "e", "Space")] == [
        True,
        True,
        False,
        False,
        False,
        False,
    ]


@pytest.mark.parametrize(
    ("kind", "autocomplete", "name"),
    [
        ("password", None, ""),
        (" PassWord ", "", "Ô nhập"),
        ("text", "current-password", ""),
        ("text", "section-a NEW-PASSWORD", ""),
        ("tel", "one-time-code", ""),
        (None, "cc-number", ""),
        ("text", "billing cc-csc", ""),
        ("text", "off", "Mật khẩu"),  # a password shown as plain text
        ("text", None, "Nhập mat khau của bạn"),
        (None, None, "Mã OTP"),
        ("number", "", "Mã xác thực (6 số)"),
        ("text", "", "CVV"),
        ("text", "", "cardNumber"),
        ("text", "", "Số thẻ"),
    ],
)
def test_a_field_the_owner_alone_fills_is_known_by_what_it_declares_or_is_called(
    kind, autocomplete, name
):
    assert a.secret_field(kind, autocomplete, name)


@pytest.mark.parametrize(
    ("kind", "autocomplete", "name"),
    [
        (None, None, ""),
        ("text", "", "Tìm kiếm"),
        ("search", "off", "Mã đơn hàng"),
        ("email", "username", "Email"),
        ("text", "cc-name", "Tên trên thẻ"),
        ("text", "cc-exp", "Ngày hết hạn"),
        ("text", "password-hint", "Gợi ý"),  # a word of its own, not the token
        ("passwordless", "", "Đăng nhập"),
        ("text", "", "Số thể thao"),  # another word than `thẻ`
    ],
)
def test_any_other_field_may_be_typed_into(kind, autocomplete, name):
    assert not a.secret_field(kind, autocomplete, name)


def test_an_action_stops_for_a_word_in_the_name_the_choice_or_under_the_element():
    plain, holding = Node("e5", "generic", ""), Node("e5", "generic", "", word="xoá")

    def word(kind: str, name: str = "", value: str = "", node: Node | None = plain) -> str:
        return a.word_for(ASK, kind, name, value, node)

    assert [word(kind, "Đặt hàng ngay") for kind in a.KINDS] == [
        "đặt hàng",  # click
        "",
        "",
        "đặt hàng",  # press
        "đặt hàng",  # select
        "",
        "",
        "",
    ]
    assert a.ASKING == ("click", "press", "select")
    # The choice made in a list counts for a list, and for nothing else.
    assert word("select", "Hành động", "Xoá tất cả") == "xoá"
    assert word("click", "Hành động", "Xoá tất cả") == ""
    # What the page drew under the element counts even when the name given holds no word.
    assert [word(kind, "Thẻ sản phẩm", node=holding) for kind in ("click", "type")] == ["xoá", ""]
    assert word("click", "Dat hang", "", holding) == "đặt hàng"  # the name is looked at first
    assert word("select", "Màu", "btn_pay", holding) == "pay"
    assert word("select", "Đặt hàng", "Xoá") == "đặt hàng"  # and the name before the choice
    assert word("click", "Tìm", node=None) == ""  # an element the model was never shown
    assert word("click", "Mùa hàng") == ""


def test_an_upload_is_a_file_that_exists_in_the_workspace(tmp_path):
    workspace, outside = tmp_path / "ws", tmp_path / "ngoai.txt"
    (workspace / "don").mkdir(parents=True)
    (workspace / "don" / "a.pdf").write_text("x")
    outside.write_text("bí mật")
    (workspace / "lien-ket").symlink_to(workspace / "don")

    assert a.upload_file(workspace, "don/a.pdf") == workspace.resolve() / "don" / "a.pdf"
    assert a.upload_file(workspace, str(workspace / "don" / "a.pdf")).name == "a.pdf"
    assert a.upload_file(workspace, "lien-ket/a.pdf").read_text() == "x"
    assert refusal(a.upload_file, workspace, "don/b.pdf\n" + "y" * 300) == (
        t.ACT_UPLOAD_MISSING.format(path="don/b.pdf " + "y" * 110)
    )
    assert refusal(a.upload_file, workspace, "don") == t.ACT_UPLOAD_MISSING.format(path="don")
    for escape in ("../ngoai.txt", str(outside), "don/../../ngoai.txt"):
        assert refusal(a.upload_file, workspace, escape) == WORKSPACE_ESCAPE
    assert refusal(lambda: a.read({"kind": "upload", "ref": "e2", "path": "x.pdf"}, workspace)) == (
        t.ACT_UPLOAD_MISSING.format(path="x.pdf")
    )
