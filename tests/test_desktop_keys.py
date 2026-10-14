"""A key combination is read here the way the helper reads it, and judged before it is sent.

The helper's own tables are the authority on what a key is: the test reads them out of the
Swift source, so a key added there and not here turns this red instead of being refused in
silence, and a key known here and not there could never be passed on unread.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from my_agent_crew.desktop import keys
from my_agent_crew.desktop.keys import CMD, CTRL, FN, OPT, SHIFT, Combo, parse

SOURCES = Path(__file__).resolve().parents[1] / "desktop-helper/Sources/DesktopHelperCore"
TABLE = re.compile(r"private static let (\w+): \[String: UInt16\] = \[(.*?)\n    \]", re.S)
ENTRY = re.compile(r'"((?:\\.|[^"\\])+)": \d+')


def helper_tables() -> dict[str, set[str]]:
    """The key names of each table in the helper's source."""
    source = (SOURCES / "KeyTable.swift").read_text(encoding="utf-8")
    return {
        name: {re.sub(r"\\(.)", r"\1", key) for key in ENTRY.findall(body)}
        for name, body in TABLE.findall(source)
    }


def held(*words: str) -> frozenset[str]:
    return frozenset(words)


def test_the_keys_read_here_are_the_helpers_own() -> None:
    tables = helper_tables()

    assert set(tables) == {"letters", "digits", "named", "punctuation", "shifted"}
    assert set().union(*tables.values()) == keys.KEYS
    assert tables["shifted"] == set(keys.SHIFTED)
    assert tables["punctuation"] == set(keys.PLAIN)
    assert tables["named"] == {*keys.NAMED, *keys.FUNCTION}


def test_the_modifier_words_are_the_helpers_own() -> None:
    source = (SOURCES / "KeyCombo.swift").read_text(encoding="utf-8")
    named = source[source.index("static func named") : source.index("default: return nil")]

    assert set(re.findall(r'"(\w+)"', named)) == set(keys.MODIFIERS)
    assert keys.MODIFIERS["alt"] == keys.MODIFIERS["opt"] == OPT


@pytest.mark.parametrize(
    ("written", "key", "modifiers"),
    [
        ("enter", "enter", held()),
        ("a", "a", held()),
        ("7", "7", held()),
        ("f12", "f12", held()),
        ("cmd+s", "s", held(CMD)),
        ("shift+tab", "tab", held(SHIFT)),
        ("ctrl+opt+shift+cmd+fn+a", "a", held(CTRL, OPT, SHIFT, CMD, FN)),
        ("alt+left", "left", held(OPT)),
        ("CMD+Shift+Z", "z", held(CMD, SHIFT)),
        ("Enter", "enter", held()),
        ("cmd+,", ",", held(CMD)),
        ("cmd+\\", "\\", held(CMD)),
        # A character typed with Shift held brings Shift with it, as the helper adds it.
        ("?", "?", held(SHIFT)),
        ("cmd+?", "?", held(CMD, SHIFT)),
        ("shift+?", "?", held(SHIFT)),
        # `+` separates and is a key too.
        ("+", "+", held(SHIFT)),
        ("cmd++", "+", held(CMD, SHIFT)),
        ("cmd+shift++", "+", held(CMD, SHIFT)),
        ("cmd+-", "-", held(CMD)),
    ],
)
def test_a_combination_is_read_as_the_helper_reads_it(written, key, modifiers) -> None:
    assert parse(written) == Combo(key, modifiers)


@pytest.mark.parametrize(
    "written",
    [
        "",
        "cmd",  # a modifier alone is no key
        "shift",
        "cmd+",  # nothing after the separator
        "+cmd",
        "++",
        "+a",  # a separator with no modifier before it
        "cmd++a",
        "cmd+cmd+a",  # one modifier twice
        "cmd+alt+opt+a",  # the same modifier under two names
        "hyper+a",
        "command+q",
        "cmd+ab",
        "f13",
        "return",
        "escape",
        "cmd + a",  # the grammar has no spaces
        " enter",
        "enter\n",
        "cmd+é",
        "cmd+ｑ",  # a full-width q
        "cmd+K",  # the Kelvin sign, which lowers to k
        "cmd-q",
        "cmd q",
    ],
)
def test_what_the_grammar_has_not_is_not_read(written) -> None:
    assert parse(written) is None


@pytest.mark.parametrize(
    ("written", "spelled"),
    [
        ("Shift+CMD+z", "shift+cmd+z"),
        ("fn+cmd+shift+alt+ctrl+a", "ctrl+opt+shift+cmd+fn+a"),
        ("alt+tab", "opt+tab"),
        ("?", "shift+?"),
        ("cmd++", "shift+cmd++"),
        ("+", "shift++"),
        ("ENTER", "enter"),
    ],
)
def test_a_combination_has_one_spelling(written, spelled) -> None:
    assert parse(written).spelled == spelled


def test_the_spelling_sent_reads_back_as_the_same_combination() -> None:
    # What the helper is sent is this program's own spelling: it has to mean what was judged.
    sets = [held(), held(CMD), held(SHIFT), held(CTRL, OPT), held(CTRL, OPT, SHIFT, CMD, FN)]
    for key in sorted(keys.KEYS):
        for modifiers in sets:
            combo = Combo(key, modifiers | (held(SHIFT) if key in keys.SHIFTED else held()))
            assert parse(combo.spelled) == combo, combo.spelled


@pytest.mark.parametrize(
    "written",
    [
        "cmd+q",
        "CMD+Q",
        "cmd+ctrl+q",  # lock the screen
        "cmd+shift+q",  # log out
        "cmd+opt+q",
        "cmd+opt+shift+q",  # log out without asking
        "fn+cmd+q",
        "cmd+shift+backspace",  # empty the Trash
        "cmd+opt+shift+backspace",  # empty it without asking
        "cmd+opt+esc",  # force quit
        "cmd+alt+esc",
        "cmd+opt+shift+esc",
    ],
)
@pytest.mark.parametrize("spotlight", [True, False])
def test_some_combinations_are_never_sent(written, spotlight) -> None:
    # One modifier more does not get past a rule, and being given Spotlight changes nothing.
    assert keys.never_sent(parse(written), spotlight=spotlight)


@pytest.mark.parametrize(
    "written",
    [
        "q",
        "shift+q",
        "ctrl+q",
        "opt+q",
        "cmd+w",
        "cmd+backspace",  # delete to the start of the line
        "shift+backspace",
        "cmd+shift+delete",  # the other delete key
        "esc",
        "cmd+esc",
        "opt+esc",
        "space",
        "shift+space",
        "ctrl+space",
        "opt+space",
    ],
)
@pytest.mark.parametrize("spotlight", [True, False])
def test_their_neighbours_are_not_refused_outright(written, spotlight) -> None:
    assert not keys.never_sent(parse(written), spotlight=spotlight)


@pytest.mark.parametrize("written", ["cmd+space", "CMD+Space", "cmd+opt+space", "cmd+shift+space"])
def test_spotlight_opens_only_for_an_agent_given_it(written) -> None:
    assert keys.never_sent(parse(written), spotlight=False)
    assert not keys.never_sent(parse(written), spotlight=True)


MOVES = ["up", "down", "left", "right", "home", "end", "pageup", "pagedown"]


@pytest.mark.parametrize(
    "written",
    [
        "tab",
        "esc",
        "backspace",
        "delete",
        *MOVES,
        "shift+tab",
        *(f"shift+{move}" for move in MOVES),
        "cmd+a",
        "cmd+c",
        "cmd+f",
        "cmd+z",
    ],
)
def test_ordinary_keys_are_sent_without_a_word(written) -> None:
    assert keys.ordinary(parse(written))


def test_the_ordinary_keys_are_those_and_no_more() -> None:
    assert len(keys.ORDINARY) == 12 + 9 + 4


@pytest.mark.parametrize("written", ["enter", "Enter", "space"])
def test_a_key_that_alone_presses_what_is_chosen(written) -> None:
    assert keys.presses(parse(written))


@pytest.mark.parametrize(
    "written", ["shift+enter", "cmd+enter", "opt+space", "tab", "esc", "a", "f5"]
)
def test_other_keys_and_those_two_with_a_modifier_held_do_not(written) -> None:
    assert not keys.presses(parse(written))


@pytest.mark.parametrize(
    "written",
    [
        "enter",  # presses whatever is chosen, and nothing in the call says what that is
        "space",
        "a",  # a character is typed with `type`, where the text rules read it
        "1",
        "?",
        "f5",
        "cmd+v",  # pastes whatever the clipboard holds
        "cmd+x",
        "cmd+s",
        "cmd+w",
        "cmd+n",
        "cmd+t",
        "cmd+tab",  # leaves the application
        "cmd+enter",  # sends, in most applications that write
        "cmd+shift+z",
        "cmd+shift+a",
        "cmd+opt+c",
        "ctrl+c",
        "opt+tab",
        "shift+enter",
        "shift+esc",
        "shift+space",
        "fn+left",
        "cmd+backspace",
        "cmd+delete",
        "ctrl+up",  # Mission Control
        "cmd+up",
    ],
)
def test_everything_else_waits_for_a_person(written) -> None:
    assert not keys.ordinary(parse(written))


def test_nothing_ordinary_is_never_sent() -> None:
    # The two lists are kept apart: a key that goes unasked is never one that is refused.
    for key, modifiers in keys.ORDINARY:
        assert not keys.never_sent(Combo(key, modifiers), spotlight=False), (key, modifiers)
