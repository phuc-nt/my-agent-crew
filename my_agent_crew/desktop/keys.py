"""A key combination, read here the way the desktop helper reads it, and what this program
thinks of it: never sent, sent without a word, or sent only once a person said yes.

The grammar is the helper's (`desktop-helper/Sources/DesktopHelperCore/KeyCombo.swift` and
`KeyTable.swift`): modifier words joined by `+`, then one key. What cannot be read here is
refused and never passed on, and the helper is sent this program's own spelling of what it
read, so the two never judge different keys. Only ASCII is read: a letter that merely lowers
to `q` is no `q` here.
"""

from __future__ import annotations

import string
from dataclasses import dataclass

CMD, SHIFT, OPT, CTRL, FN = "cmd", "shift", "opt", "ctrl", "fn"
MODIFIERS = {"cmd": CMD, "shift": SHIFT, "opt": OPT, "alt": OPT, "ctrl": CTRL, "fn": FN}
SPELLED_IN = (CTRL, OPT, SHIFT, CMD, FN)
ARROWS = ("up", "down", "left", "right")
MOVES = (*ARROWS, "home", "end", "pageup", "pagedown")
NAMED = ("enter", "tab", "space", "esc", "backspace", "delete", *MOVES)
FUNCTION = tuple(f"f{number}" for number in range(1, 13))
PLAIN = "=-][';\\,/.`"
# Characters typed with Shift held: the helper adds Shift for them, and so does this.
SHIFTED = '!@#$^%(&*)+_}{":|<?>~'
KEYS = frozenset((*string.ascii_lowercase, *string.digits, *NAMED, *FUNCTION, *PLAIN, *SHIFTED))


@dataclass(frozen=True)
class Combo:
    key: str
    held: frozenset[str]

    @property
    def spelled(self) -> str:
        """The one spelling of this combination, which the helper reads back as the same."""
        return "+".join([*(word for word in SPELLED_IN if word in self.held), self.key])


def parse(text: str) -> Combo | None:
    """The combination `text` writes, or None for anything the helper's grammar has not."""
    if not text.isascii():
        return None
    lowered = text.lower()
    # `+` is the separator and a key too: `cmd++` is Command with plus, `+` alone is plus.
    if lowered == "+":
        words, key = [], "+"
    elif lowered.endswith("++"):
        words, key = lowered[:-2].split("+"), "+"
    elif "+" in lowered:
        head, _, key = lowered.rpartition("+")
        words = head.split("+")
    else:
        words, key = [], lowered
    if key not in KEYS:
        return None
    held: set[str] = set()
    for word in words:
        modifier = MODIFIERS.get(word)
        if modifier is None or modifier in held:  # an empty word, an unknown one, one twice
            return None
        held.add(modifier)
    if key in SHIFTED:
        held.add(SHIFT)
    return Combo(key, frozenset(held))


# Never sent, whatever a person would say: quit an application, empty the Trash, lock the
# screen or log out, force quit. A rule holds when its modifiers are all held, as the helper's
# own do; one modifier more does not get past it.
NEVER = (
    ("q", frozenset({CMD})),
    ("backspace", frozenset({CMD, SHIFT})),
    ("esc", frozenset({CMD, OPT})),
)
# Opens Spotlight, which starts anything on the machine: only for an agent given Spotlight.
SPOTLIGHT = ("space", frozenset({CMD}))
# What goes through like a click does: moving about, confirming, leaving, and the handful of
# combinations that only select, copy, find and undo. Everything else waits for a person.
ORDINARY = frozenset(
    {
        *((key, frozenset()) for key in NAMED),
        *((key, frozenset({SHIFT})) for key in ("tab", *MOVES)),
        *((key, frozenset({CMD})) for key in ("a", "c", "f", "z")),
    }
)


def _holds(combo: Combo, rule: tuple[str, frozenset[str]]) -> bool:
    key, held = rule
    return combo.key == key and combo.held >= held


def never_sent(combo: Combo, spotlight: bool) -> bool:
    """Whether the combination is refused outright. `spotlight` says whether the agent was
    given Spotlight."""
    if any(_holds(combo, rule) for rule in NEVER):
        return True
    return _holds(combo, SPOTLIGHT) and not spotlight


def ordinary(combo: Combo) -> bool:
    return (combo.key, combo.held) in ORDINARY
