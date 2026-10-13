"""What an agent's own settings say of a page and of a name on it: whether a host is one the
agent was given, and whether a name holds one of the words that stop for a person.

Both are soft guards, the owner's to change. The hard refusals (private addresses, password
fields) are elsewhere and read no setting."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from urllib.parse import urlsplit

# Letters and digits in a row. An underscore joins nothing: `btn_pay` holds the word `pay`.
WORD = re.compile(r"[^\W_]+")
# Where a name written without spaces changes word: `CheckOut` reads as `check out`.
HUMP = re.compile(r"(?<=[a-z])(?=[A-Z])")


def host_of(url: str) -> str:
    """The host a URL names, as a certificate would spell it: lower case, no trailing dot,
    no port, a name in another script in its ASCII form. "" for what names none."""
    try:
        host = (urlsplit(url).hostname or "").rstrip(".")  # already lower case
        return host.encode("idna").decode("ascii") if host else ""
    except ValueError:  # a bad bracket or port, or a label no name can hold
        return ""


def host_allowed(host: str, patterns: Sequence[str]) -> bool:
    """Whether `host` is one of the agent's own. `shop.example` is that host alone;
    `*.shop.example` is it and everything under it. A host that merely ends the same way
    (`notshop.example`) is neither."""
    if not host:
        return False
    for pattern in patterns:
        if pattern.startswith("*."):
            if host == pattern[2:] or host.endswith(pattern[1:]):
                return True
        elif host == pattern:
            return True
    return False


def words(text: str) -> list[str]:
    """The words of a name, lower case and in one spelling of each accented letter."""
    return WORD.findall(unicodedata.normalize("NFC", HUMP.sub(" ", text)).casefold())


def plain(word: str) -> str:
    """A word as someone types it without accents. `đ` is a letter of its own and no marked
    `d`, so it is replaced before the marks are taken off."""
    apart = unicodedata.normalize("NFD", word.replace("đ", "d"))
    return "".join(ch for ch in apart if not unicodedata.combining(ch))


class AskWords:
    """The words of one agent that stop an action for a person. A pattern matches where its
    words stand in a name as whole words, in a row. A word of the name may also be the
    pattern's word typed without its accents (`Dat hang` is `đặt hàng`); the name's own
    accents are never taken off, so one written with others is another word (`mùa` is not
    `mua`)."""

    def __init__(self, patterns: Sequence[str]) -> None:
        split = ((pattern, words(pattern)) for pattern in patterns)
        self._patterns = [(p, want, [plain(w) for w in want]) for p, want in split if want]

    def __bool__(self) -> bool:
        return bool(self._patterns)

    def find(self, text: str) -> str:
        """The first pattern `text` holds, or ""."""
        have = words(text)
        if not have:
            return ""
        for pattern, want, bare in self._patterns:
            for start in range(len(have) - len(want) + 1):
                if all(
                    word in (want[i], bare[i])
                    for i, word in enumerate(have[start : start + len(want)])
                ):
                    return pattern
        return ""
