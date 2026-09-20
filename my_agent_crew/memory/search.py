"""Finding a thought in the memory files, rather than finding a line.

A note is written in bullets and paragraphs, and one thought often runs over several
lines — "- Jimny 5 cửa,\n  ngân sách 1.5 tỷ" is one item, not two. Matching line by line
loses exactly those, so the unit here is the entry: a bullet with its continuation lines,
or a paragraph. Accents are dropped for matching, because a person searching their own
notes from a phone types `sach dang doc` and means `sách đang đọc`.

Pure functions over text: the caller reads the files and decides which ones to pass.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

MAX_CHARS = 300
BULLETS = ("- ", "* ", "+ ")
# Below this length a word is inside almost every entry — Vietnamese without accents is
# full of `o`, `ma`, `an` — so short words have to be found whole to count at all.
SUBSTRING_MIN_CHARS = 3


@dataclass(frozen=True)
class Entry:
    """One thought, with the heading it sits under as its context."""

    heading: str
    text: str
    order: int


@dataclass(frozen=True)
class Hit:
    source: str
    text: str
    score: int
    found: int


def normalize(text: str) -> str:
    """Lowercase and without accents, so `suc khoe` and `Sức khoẻ` are the same word.

    `đ` needs its own line: it is a letter of the Vietnamese alphabet rather than a `d`
    with a mark, so decomposition leaves it alone and `doc` would never reach `đọc`.
    """
    decomposed = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def terms_of(query: str) -> list[str]:
    return [t for t in normalize(query).split() if t]


def _is_bullet(line: str) -> bool:
    stripped = line.lstrip()
    if stripped.startswith(BULLETS):
        return True
    head, _, rest = stripped.partition(". ")
    return bool(rest) and head.isdigit()


def split_entries(text: str) -> list[Entry]:
    """Bullets keep their indented continuation lines; anything else groups into paragraphs."""
    entries: list[Entry] = []
    heading = ""
    current: list[str] = []

    def flush() -> None:
        if current:
            entries.append(Entry(heading, "\n".join(current).strip(), len(entries)))
            current.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush()
        elif line.lstrip().startswith("#"):
            flush()
            heading = line.lstrip("#").strip()
        else:
            if _is_bullet(line):
                flush()
            current.append(line)
    flush()
    return entries


def score(entry: Entry, terms: list[str]) -> tuple[int, int]:
    """`(words found, score)` for this entry, heading included.

    A word found whole scores double, because dropping accents makes short words
    promiscuous: `doc` is inside `docs` as surely as it is inside `đọc`, and the entry
    that has the word itself is the one worth reading first. A word shorter than
    `SUBSTRING_MIN_CHARS` only counts when found whole. The count stays separate from the
    score so "has every word" does not depend on how each one was found.
    """
    haystack = normalize(f"{entry.heading}\n{entry.text}")
    words = set(re.findall(r"\w+", haystack))
    found = [
        term
        for term in terms
        if term in words or (len(term) > SUBSTRING_MIN_CHARS and term in haystack)
    ]
    return len(found), sum(2 if term in words else 1 for term in found)


def _shorten(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= MAX_CHARS else flat[: MAX_CHARS - 1] + "…"


def search(files: list[tuple[str, str]], query: str, limit: int) -> list[Hit]:
    """The best entries across `(source, text)` files, already in the order to show.

    Files come in the order the caller wants them tried — shared facts first, then the
    newest notes — and that order breaks ties, so a fresh note outranks an old one at the
    same score. When some entry has every word, entries missing one are dropped: a partial
    match next to a full one is noise.
    """
    terms = terms_of(query)
    if not terms:
        return []
    hits: list[Hit] = []
    for source, text in files:
        for entry in split_entries(text):
            found, points = score(entry, terms)
            if found:
                label = f"{source} › {entry.heading}" if entry.heading else source
                hits.append(Hit(label, _shorten(entry.text), points, found))
    if not hits:
        return []
    if any(h.found == len(terms) for h in hits):
        hits = [h for h in hits if h.found == len(terms)]
    hits.sort(key=lambda h: -h.score)
    return hits[:limit]
