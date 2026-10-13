"""The outline of a page as the model is given it: whole when it fits, cut down to what can
be acted on when it does not, or only the lines that hold what was asked for."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from my_agent_crew.browser.snapshot import Snapshot

# What a long page is cut down to: the things a person would act on, and the headings that
# say where on the page they are.
LISTED = frozenset(
    "button link textbox searchbox combobox listbox checkbox radio switch slider spinbutton "
    "tab menuitem menuitemcheckbox menuitemradio treeitem heading".split()
)
TREE, LIST, QUERY = "tree", "list", "query"


@dataclass(frozen=True)
class View:
    text: str
    kind: str
    shown: int  # lines given
    total: int  # lines there were to give


def _folded(text: str) -> str:
    """Text as a search compares it: one spelling of each accented letter, one space between
    words, no case."""
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()


def _fit(drawn: list[str], budget: int, kind: str) -> View:
    """As many whole lines as the budget holds: a line cut in half would read as a name."""
    kept, used = 0, 0
    for line in drawn:
        if used + len(line) + 1 > budget:
            break
        kept, used = kept + 1, used + len(line) + 1
    return View("\n".join(drawn[:kept]), kind, kept, len(drawn))


def view(snapshot: Snapshot, budget: int, *, listed: bool = False, query: str = "") -> View:
    """The outline as the model is given it. Whole when it fits; cut down to what can be
    acted on when it does not, or when asked; or only the lines that hold `query`, each
    under the lines it stands under."""
    lines = snapshot.lines
    if query.strip():
        needle = _folded(query)
        keep: set[int] = set()
        for i, line in enumerate(lines):
            if needle in _folded(line.text):
                while i >= 0 and i not in keep:
                    keep.add(i)
                    i = lines[i].parent
        drawn = [" " * ln.indent + ln.drawn for i, ln in enumerate(lines) if i in keep]
        return _fit(drawn, budget, QUERY)
    whole = [" " * line.indent + line.drawn for line in lines]
    if not listed and sum(len(line) + 1 for line in whole) <= budget:
        return View("\n".join(whole), TREE, len(whole), len(whole))
    drawn, top = [], set()
    for i, line in enumerate(lines):
        if line.ref and (line.role in LISTED or line.pointer):
            top.add(i)
            drawn.append(line.drawn)
        elif line.parent in top and (line.role.startswith("/") or line.role == "option"):
            drawn.append("  " + line.drawn)
    return _fit(drawn, budget, LIST)
