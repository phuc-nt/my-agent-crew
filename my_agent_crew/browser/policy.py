"""What an agent's own settings say of a page and of a name on it: whether a host is one the
agent was given, and whether a name holds one of the words that stop for a person.

Both are soft guards, the owner's to change. The hard refusals (private addresses, password
fields) are elsewhere and read no setting."""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

# Letters and digits in a row. An underscore joins nothing: `btn_pay` holds the word `pay`.
WORD = re.compile(r"[^\W_]+")
# Where a name written without spaces changes word: `CheckOut` reads as `check out`.
HUMP = re.compile(r"(?<=[a-z])(?=[A-Z])")
# What a browser draws nothing for (Unicode's default ignorable code points): a soft hyphen
# or a zero-width space in the middle of `pay` leaves a name that still reads `pay`.
UNSEEN = re.compile(
    "[\u00ad\u034f\u061c\u17b4\u17b5\u180b-\u180f\u200b-\u200f\u202a-\u202e\u2060-\u206f"
    "\ufe00-\ufe0f\ufeff\ufff0-\ufff8\U0001bca0-\U0001bca3\U0001d173-\U0001d17a"
    "\U000e0000-\U000e0fff]"
)
# Letters by their class that are drawn as an empty place: they part two words.
BLANK = re.compile("[\u115f\u1160\u3164\uffa0]")
# A host as a browser is handed it: labels of letters, digits, hyphens and underscores.
LABELS = re.compile(r"(?:[a-z0-9_-]+\.)*[a-z0-9_-]+\.?")
# One part of a host written in numbers, in the bases a browser reads: hex after `0x` (and
# nothing after it is zero), octal after a leading `0`, decimal otherwise.
NUMBER = re.compile(r"0x(?P<hex>[0-9a-f]*)|0(?P<oct>[0-7]+)|(?P<dec>0|[1-9][0-9]*)")


@dataclass(frozen=True)
class Address:
    url: str  # the address as the browser is given it
    scheme: str
    host: str  # as a certificate would spell it: lower case, ASCII, no trailing dot, no port
    port: int | None


def _number(part: str) -> int | None:
    read = NUMBER.fullmatch(part)
    if not read:
        return None
    if read["dec"] is not None:
        return int(read["dec"])
    return int(read["oct"], 8) if read["oct"] is not None else int(read["hex"] or "0", 16)


def _plain(host: str) -> str:
    """A host that ends in a number is an address to a browser, in any base and in one part
    to four: `2130706433`, `0x7f.1` and `0177.0.0.1` are all 127.0.0.1. That address the plain
    way; a name as it is; ValueError for what ends in a number and is no address, which a
    browser does not open."""
    parts = host.removesuffix(".").split(".")
    if not parts[-1].isdigit() and _number(parts[-1]) is None:
        return host
    *first, last = [_number(part) for part in parts]
    if len(first) > 3 or last is None or None in first or any(n > 255 for n in first):
        raise ValueError(host)
    if last >= 256 ** (4 - len(first)):  # the last part fills every byte the others left
        raise ValueError(host)
    return str(ipaddress.IPv4Address(last + sum(n << 8 * (3 - at) for at, n in enumerate(first))))


def read_address(url: str) -> Address | None:
    """An address read the one way a browser reads it too, or None.

    The host this reads is what a rule is judged on, so an address a browser might read
    another way is no address at all: a backslash before the path (a browser takes it for a
    slash, and the host ends there), a name and password before the host, an escaped letter
    in the host, a blank anywhere. A host in another script is turned into its ASCII form
    here, and one written in numbers into the address it stands for; the browser is given
    that spelling and not the one it would work out."""
    if not url.isprintable() or " " in url:
        return None
    try:
        parts = urlsplit(url)
        port = parts.port
        if not parts.netloc or "@" in parts.netloc:
            return None
        if parts.netloc.startswith("["):
            host = str(ipaddress.IPv6Address(parts.hostname or ""))
            spelled = f"[{host}]"
        else:
            host = (parts.hostname or "").encode("idna").decode("ascii")
            if not LABELS.fullmatch(host):
                return None
            host = spelled = _plain(host)
    except ValueError:  # a bad bracket or port, a label no name can hold, numbers no address
        return None
    netloc = spelled if port is None else f"{spelled}:{port}"
    return Address(parts._replace(netloc=netloc).geturl(), parts.scheme, host.rstrip("."), port)


def host_of(url: str) -> str:
    """The host a URL names, "" for what names none or names it in a way to be misread."""
    address = read_address(url)
    return address.host if address else ""


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
    """The words of a name as an eye reads them: lower case, one spelling of each accented
    letter, a letter drawn in another form (full width, a ligature) as the plain one, and
    nothing of what is not drawn or is a mark over a letter that makes no letter with it.
    A letter of another alphabet that looks the same is not read as the one it looks
    like."""
    seen = unicodedata.normalize("NFKC", BLANK.sub(" ", UNSEEN.sub("", text)))
    letters = "".join(ch for ch in seen if unicodedata.category(ch) not in ("Mn", "Me"))
    return WORD.findall(HUMP.sub(" ", letters).casefold())


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
