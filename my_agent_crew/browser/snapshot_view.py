"""The outline of a page as the model is given it: whole when it fits, cut down to what can
be acted on when it does not, or only the lines that hold what was asked for. A line is
marked when its element was not on the page the model was last shown in that tab."""

from __future__ import annotations

import unicodedata
from collections import Counter
from collections.abc import Collection
from dataclasses import dataclass

from my_agent_crew.browser.fence import whole_lines
from my_agent_crew.browser.snapshot import Shown, Snapshot, traits, with_mark

# What a long page is cut down to: the things a person would act on, and the headings that
# say where on the page they are.
LISTED = frozenset(
    "button link textbox searchbox combobox listbox checkbox radio switch slider spinbutton "
    "tab menuitem menuitemcheckbox menuitemradio treeitem heading".split()
)
TREE, LIST, QUERY = "tree", "list", "query"
# Written among a line's own attributes; what it means is said outside the fence.
NEW = "[new]"


@dataclass(frozen=True)
class View:
    text: str
    kind: str
    shown: int  # lines given
    total: int  # lines there were to give
    new: int = 0  # lines given with the mark


def added(before: Shown | None, url: str, now: Snapshot) -> frozenset[str]:
    """Refs of the elements that came, or changed what they say, since the model was last
    shown this page: one of that role and text was not there then, or fewer of them were.

    An element that kept its ref is paired with itself first, so of several alike the one
    marked is the one that came. A page that draws itself again gives every element a ref
    anew, and those pair with what is left in the order they are drawn. Nothing is new on a
    page at another address, nor where nothing that says anything is left of what was shown:
    all of that page is, and a mark on every line would point at none."""
    if before is None or before.url != url:
        return frozenset()
    here = traits(now)
    left = Counter(before.traits.values())
    loose = [ref for ref, trait in here.items() if before.traits.get(ref) != trait]
    left.subtract(trait for ref, trait in here.items() if before.traits.get(ref) == trait)
    fresh = set()
    for ref in loose:
        if left[here[ref]] > 0:
            left[here[ref]] -= 1
        else:
            fresh.add(ref)
    stayed = any(text for ref, (_role, text) in here.items() if ref not in fresh)
    return frozenset(fresh) if stayed else frozenset()


def _folded(text: str) -> str:
    """Text as a search compares it: one spelling of each accented letter, one space between
    words, no case."""
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()


def _fit(drawn: list[tuple[str, bool]], budget: int, kind: str) -> View:
    """As many whole lines as the budget holds, and how many of them carry the mark."""
    given = drawn[: whole_lines([line for line, _new in drawn], budget)]
    text = "\n".join(line for line, _new in given)
    return View(text, kind, len(given), len(drawn), sum(new for _line, new in given))


def view(
    snapshot: Snapshot,
    budget: int,
    *,
    listed: bool = False,
    query: str = "",
    fresh: Collection[str] = (),
) -> View:
    """The outline as the model is given it. Whole when it fits; cut down to what can be
    acted on when it does not, or when asked; or only the lines that hold `query`, each
    under the lines it stands under. A line whose ref is in `fresh` carries the mark."""
    lines = snapshot.lines

    def row(i: int, indent: str) -> tuple[str, bool]:
        new = lines[i].ref in fresh
        return indent + (with_mark(lines[i], NEW) if new else lines[i].drawn), new

    if query.strip():
        needle = _folded(query)
        keep: set[int] = set()
        for i, line in enumerate(lines):
            if needle in _folded(line.text):
                while i >= 0 and i not in keep:
                    keep.add(i)
                    i = lines[i].parent
        found = [row(i, " " * ln.indent) for i, ln in enumerate(lines) if i in keep]
        return _fit(found, budget, QUERY)
    whole = _fit([row(i, " " * line.indent) for i, line in enumerate(lines)], budget, TREE)
    if not listed and whole.shown == whole.total:
        return whole
    drawn, top = [], set()
    for i, line in enumerate(lines):
        if line.ref and (line.role in LISTED or line.pointer):
            top.add(i)
            drawn.append(row(i, ""))
        elif line.parent in top and (line.role.startswith("/") or line.role == "option"):
            drawn.append(row(i, "  "))
    return _fit(drawn, budget, LIST)
