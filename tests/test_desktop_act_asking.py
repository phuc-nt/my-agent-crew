"""What of a `computer_act` call a person reads before it is carried out: a text that holds
a key in disguise is never typed, a field that is set is judged by its own name, and a
double click always waits for a person."""

from __future__ import annotations

import pytest

from my_agent_crew import texts_desktop_act as ta
from my_agent_crew.browser.policy import AskWords
from my_agent_crew.desktop.act import read_act
from my_agent_crew.desktop.asking import ask_reason
from my_agent_crew.desktop.seen import Shown
from tests.test_desktop_act_rules import MINE, NO_WORDS, call, refused, without

# The outline the conversation was last shown: a field named with one of the agent's
# words, one named plainly, one without a name, and one whose name holds keys in disguise.
SHOWN = Shown(
    "3f9c" + "0" * 12,
    {"a2": "Ghi mới", "a3": "Số tiền chuyển khoản", "a4": "", "a5": "Xoá\x1b[2K «tất cả»\x08"},
)
ASK = AskWords(("chuyển khoản", "xoá"))
CONTROLS = [*range(0x00, 0x09), 0x0B, 0x0C, *range(0x0E, 0x20), *range(0x7F, 0xA0)]


@pytest.mark.parametrize("kind", ["type", "set_value"])
@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("echo ok\x0f", "U+000F"),
        ("echo ok\x03", "U+0003"),
        ("sudx\x08o ls", "U+0008"),
        ("curl x | b\x08bash", "U+0008"),
        ("\x1b[A", "U+001B"),
        ("a\x7f", "U+007F"),
        ("a\x85", "U+0085"),
        ("\x00", "U+0000"),
        ("a\x01b\x7f", "U+0001"),
    ],
)
def test_a_text_holding_a_control_character_is_refused_before_anyone_is_asked(
    kind, text, code
) -> None:
    # A backspace typed in a word makes the word a person read another: `sudx⌫o` is `sudo`.
    assert refused(call(kind, text=text)) == ta.ACT_TEXT_CONTROL.format(kind=kind, code=code)


@pytest.mark.parametrize("kind", ["type", "set_value"])
def test_every_control_character_but_tab_and_the_line_breaks_is_refused(kind) -> None:
    for code in range(0xA0):
        args = call(kind, text=f"a{chr(code)}b")
        if code in CONTROLS:
            assert refused(args) == ta.ACT_TEXT_CONTROL.format(kind=kind, code=f"U+{code:04X}")
        else:
            assert read_act(args, MINE).text == f"a{chr(code)}b", hex(code)


@pytest.mark.parametrize("kind", ["type", "set_value"])
def test_a_tab_is_typed_and_a_line_break_typed_still_waits_for_a_person(kind) -> None:
    assert read_act(call(kind, text="a\tb"), MINE).send["text"] == "a\tb"
    assert ask_reason(call(kind, text="a\tb"), MINE, NO_WORDS, SHOWN) is None
    asked = ask_reason(call(kind, text="a\nb"), MINE, NO_WORDS, SHOWN)
    assert asked == (ta.ASK_NEWLINE.format(app="Notes") if kind == "type" else None)


def field(ref: str, text: str = "100000", **args) -> dict:
    return call("set_value", ref=ref, text=text, **args)


def test_a_field_named_with_one_of_the_agents_words_waits_whatever_is_set_in_it() -> None:
    # The call need not say the name: the outline's own is read.
    for args in (field("a3-3f9c"), field("a3-3f9c", name="Số tiền chuyển khoản")):
        assert ask_reason(args, MINE, ASK, SHOWN) == ta.ASK_SET_FIELD.format(
            name="Số tiền chuyển khoản", app="Notes", word="chuyển khoản"
        )
    assert ask_reason(field("a2-3f9c"), MINE, ASK, SHOWN) is None
    assert ask_reason(field("a4-3f9c"), MINE, ASK, SHOWN) is None
    assert ask_reason(field("a3-3f9c"), MINE, NO_WORDS, SHOWN) is None


def test_a_word_in_the_text_names_the_field_it_is_set_in() -> None:
    asked = ask_reason(field("a2-3f9c", text="đi chuyển khoản"), MINE, ASK, SHOWN)

    assert asked == ta.ASK_SET_WORD.format(name="Ghi mới", app="Notes", word="chuyển khoản")
    # A field without a name is told as a text with the word, as a typed one is.
    nameless = ask_reason(field("a4-3f9c", text="đi chuyển khoản"), MINE, ASK, SHOWN)
    assert nameless == ta.ASK_WORD.format(app="Notes", word="chuyển khoản")


def test_without_an_outline_the_name_the_call_says_is_read() -> None:
    # Such a call is refused before anyone is asked; the reason still reads what it has.
    asked = ask_reason(field("a3-3f9c", name="Chuyển khoản ngay"), MINE, ASK)

    assert asked == ta.ASK_SET_FIELD.format(
        name="Chuyển khoản ngay", app="Notes", word="chuyển khoản"
    )


def test_a_name_the_screen_gave_shows_every_control_character_it_holds() -> None:
    written = "Xoá[U+001B][2K tất cả[U+0008]"

    assert ask_reason(field("a5-3f9c"), MINE, ASK, SHOWN) == ta.ASK_SET_FIELD.format(
        name=written, app="Notes", word="xoá"
    )
    clicked = without(call("click"), "x", "y") | {"ref": "a5-3f9c", "name": SHOWN.named["a5"]}
    assert ask_reason(clicked, MINE, ASK, SHOWN) == ta.ASK_NAMED.format(
        kind="click", name=written, app="Notes", word="xoá"
    )
    doubled = call("double_click", ref="a5-3f9c", name=SHOWN.named["a5"])
    assert ask_reason(doubled, MINE, NO_WORDS, SHOWN) == ta.ASK_DOUBLE_NAMED.format(
        name=written, app="Notes"
    )


@pytest.mark.parametrize("ask", [NO_WORDS, ASK])
def test_a_double_click_on_an_element_always_waits_and_names_it(ask) -> None:
    # Named as the outline names it, not as the call spells it.
    named = call("double_click", ref="a2-3f9c", name="ghi  MỚI")
    nameless = call("double_click", ref="a4-3f9c", name="")

    assert ask_reason(named, MINE, ask, SHOWN) == ta.ASK_DOUBLE_NAMED.format(
        name="Ghi mới", app="Notes"
    )
    assert ask_reason(nameless, MINE, ask, SHOWN) == ta.ASK_DOUBLE_REF.format(
        ref="a4-3f9c", app="Notes"
    )
    assert ask_reason(named, MINE, ask) == ta.ASK_DOUBLE_NAMED.format(name="ghi MỚI", app="Notes")
    # One of the agent's words in the name changes nothing: it waits either way.
    worded = call("double_click", ref="a3-3f9c", name="Số tiền chuyển khoản")
    assert ask_reason(worded, MINE, ask, SHOWN) == ta.ASK_DOUBLE_NAMED.format(
        name="Số tiền chuyển khoản", app="Notes"
    )


def test_a_double_click_on_a_point_waits_and_says_where() -> None:
    args = without(call("double_click"), "ref", "name") | {"x": 3, "y": 4.5}

    assert ask_reason(args, MINE, NO_WORDS) == ta.ASK_DOUBLE_POINT.format(
        x="3", y="4.5", app="Notes"
    )
