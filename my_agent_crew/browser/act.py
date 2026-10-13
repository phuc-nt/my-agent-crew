"""What an action on a page is judged by before a browser is asked anything: which kinds
there are and what each needs, which keys may be pressed, which fields are never typed into,
and which names stop for a person.

The words that stop for a person are the agent's own setting. The fields never typed into
are no setting: a password, a one-time code and a card number are the owner's to enter."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from my_agent_crew import texts_browser as t
from my_agent_crew.browser.policy import AskWords
from my_agent_crew.browser.snapshot import Node
from my_agent_crew.tools.registry import ToolError
from my_agent_crew.tools.workspace import resolve_inside

KINDS = ("click", "type", "fill", "press", "select", "hover", "scroll", "upload")
# The kinds that set something off: only these stop for a word in a name.
ASKING = ("click", "press", "select")
# The kinds that put keys into whatever holds the cursor.
KEYBOARD = ("type", "fill", "press")
NEEDS = {"type": "text", "fill": "text", "press": "key", "select": "value", "upload": "path"}
# No chord but Shift: a shortcut is the browser's or the site's, and does what no name says.
KEYS = (
    "Enter",
    "Tab",
    "Escape",
    "Backspace",
    "Delete",
    "Space",
    "ArrowUp",
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
    "Home",
    "End",
    "PageUp",
    "PageDown",
)
SHIFT = "Shift+"
SECRET_AUTOCOMPLETE = frozenset(
    {"current-password", "new-password", "one-time-code", "cc-number", "cc-csc"}
)
PATH_CHARS = 120
_NAMED = {name.casefold(): name for name in KEYS}
_SECRET = AskWords(t.SECRET_FIELD_WORDS)


@dataclass(frozen=True)
class Asked:
    """One action as the model asked for it, once it is known to be one that can be made."""

    kind: str
    ref: str
    name: str
    text: str = ""
    key: str = ""  # as the browser spells it
    value: str = ""
    file: Path | None = None


def _text(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    return value.strip() if isinstance(value, str) else ""


def key_of(key: str) -> str:
    """A key as the browser spells it: one from the list or one character, with Shift at
    most. Anything else is refused."""
    shift = key[: len(SHIFT)].casefold() == SHIFT.casefold()
    base = key[len(SHIFT) :] if shift else key
    named = _NAMED.get(base.casefold())
    letter = len(base) == 1 and base.isascii() and base.isprintable() and not base.isspace()
    if named or (letter and (base.isalnum() or not shift)):
        return (SHIFT if shift else "") + (named or base)
    said = " ".join(key.split())[:40]
    raise ToolError(t.ACT_KEY.format(key=said, keys=", ".join(KEYS)))


def sends(key: str) -> bool:
    """Whether a key is the one that sends the form it is pressed in."""
    return key.removeprefix(SHIFT) == "Enter"


def secret_field(kind: str | None, autocomplete: str | None, name: str) -> bool:
    """Whether a field is one the owner alone fills: by what the page declares it to be, or
    by what it is called (a password shown as plain text is still a password)."""
    if (kind or "").strip().casefold() == "password":
        return True
    if SECRET_AUTOCOMPLETE & set((autocomplete or "").casefold().split()):
        return True
    return bool(_SECRET.find(name))


def word_for(ask: AskWords, kind: str, name: str, value: str, node: Node | None) -> str:
    """The word for which this action stops for a person, "" for none: in the name the
    model gave, in the choice it makes, or in what the page drew at and under the element."""
    if kind not in ASKING:
        return ""
    chosen = ask.find(value) if kind == "select" else ""
    return ask.find(name) or chosen or (node.word if node else "")


def upload_file(workspace: Path, path: str) -> Path:
    """The file an upload hands the page: one that exists in the agent's workspace."""
    file = resolve_inside(workspace, path)
    try:
        found = file.is_file()
    except OSError:  # a name no file can have
        found = False
    if not found:
        raise ToolError(t.ACT_UPLOAD_MISSING.format(path=" ".join(path.split())[:PATH_CHARS]))
    return file


def _missing(kind: str, args: dict[str, Any]) -> str:
    """The argument this kind needs and was not given, "" when it has them all."""
    if not _text(args, "ref"):
        return "ref"
    what = NEEDS.get(kind, "")
    if what == "text":
        raw = args.get("text")
        # `fill` may be given nothing to write, which empties the field; `type` may not.
        return "" if isinstance(raw, str) and (raw or kind == "fill") else "text"
    return "" if not what or _text(args, what) else what


def read(args: dict[str, Any], workspace: Path) -> Asked:
    """The action the arguments ask for, or the refusal that says what is wrong with them."""
    kind = _text(args, "kind")
    if kind not in KINDS:
        said = " ".join(kind.split())[:40]
        raise ToolError(t.ACT_KIND.format(kind=said, kinds=", ".join(KINDS)))
    missing = _missing(kind, args)
    if missing:
        raise ToolError(t.ACT_NEEDS.format(kind=kind, what=missing))
    what = NEEDS.get(kind)
    # Typed text is taken as written: a space at either end is a key like any other.
    text = args["text"] if what == "text" else ""
    if kind == "type" and ("\n" in text or "\r" in text):
        raise ToolError(t.ACT_NEWLINE)
    return Asked(
        kind=kind,
        ref=_text(args, "ref"),
        name=_text(args, "name"),
        text=text,
        key=key_of(_text(args, "key")) if what == "key" else "",
        value=_text(args, "value") if what == "value" else "",
        file=upload_file(workspace, _text(args, "path")) if what == "path" else None,
    )
