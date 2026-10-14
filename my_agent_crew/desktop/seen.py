"""What a conversation was last shown of an application, and what a ref may mean by it.

The helper numbers the elements from 1 again in every outline, so `a4` of one outline is
another element in the next. A ref is therefore shown with a tag of its outline, and an
action by ref is held to the outline the conversation itself was last shown: a ref of an
outline before it, of one another conversation read, or of a row that did not fit the answer
is refused here, before anybody is asked and before the helper hears of it. The helper holds
the same line on its side: it takes a ref only with the name of the outline it gave last.

A click by ref says the name it read beside the ref as well, and a field that is set may.
A person is shown that name on the approval card, so it has to be the name the outline gave,
and is refused when it is not. The agent's own words are looked for in the outline's name
itself (`asking.py`), so a field that is set is judged by its name whether the call says it
or not.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from my_agent_crew import texts_desktop_act as ta
from my_agent_crew.browser.kit import one_line

if TYPE_CHECKING:
    from my_agent_crew.desktop.act import Act

# The name the helper gives an outline, and how much of it a ref shows.
OUTLINE = re.compile(r"[0-9a-f]{16}")
TAG = 4
# A ref as an outline shows it: the helper's own ref, then the tag of the outline.
TOKEN = re.compile(r"(a[0-9]{1,6})-([0-9a-f]{4})")
NAME_CHARS = 80


@dataclass(frozen=True)
class Shown:
    """One outline as a conversation was shown it."""

    outline: str
    # What each row that fitted the answer was called: its title, or what it held without one.
    named: Mapping[str, str] = field(default_factory=dict)
    # The secure fields of the whole outline, and not only of what fitted.
    secure: frozenset[str] = frozenset()


def _plain(name: str) -> str:
    return " ".join(unicodedata.normalize("NFC", name).split()).casefold()


def same_name(one: str, other: str) -> bool:
    """Two names a person would read as the same: spacing and case aside, and however the
    marks of a letter are written (this system writes a file's name with them apart)."""
    return _plain(one) == _plain(other)


def ref_refusal(act: Act, shown: Shown | None) -> str:
    """The sentence an action by ref is refused with for what its conversation was last
    shown, or "". An action that names no ref is not this module's to judge."""
    if not act.ref:
        return ""
    if shown is None or shown.outline[:TAG] != act.tag:
        return ta.ACT_REF_UNSEEN.format(ref=act.token)
    # Before whether its row fitted the answer: a secure field is one wherever it stood.
    if act.text is not None and act.ref in shown.secure:
        return ta.ACT_SECURE_REF.format(ref=act.token)
    if act.ref not in shown.named:
        return ta.ACT_REF_UNSEEN.format(ref=act.token)
    # A click says its name always, an empty one included; a field that is set, when it will.
    said = act.text is None or bool(act.name)
    if said and not same_name(act.name, shown.named[act.ref]):
        name = one_line(act.name, NAME_CHARS)
        return ta.ACT_NAME_MISMATCH.format(ref=act.token, name=name)
    return ""
