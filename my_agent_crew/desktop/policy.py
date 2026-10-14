"""The rules of the desktop that read no helper: which applications are an agent's own, and
what is never typed into any of them.

An application is an agent's when the agent's list names it: by its name, whatever the
case and however its accents are encoded, or by its bundle id, letter for letter. A web
browser never is, whatever the list says (`browsers.py`). The text rules are hard refusals:
they hold for every agent and no setting turns them off. A text is judged as a shell would
read it: a line carried on with a backslash is one line, and the quotes and backslashes a
shell takes out of a word are taken out. They are a tripwire for the plain spellings and
not a wall, since text can be typed in pieces; what an agent types is still a call a person
approves unless the conversation runs on its own.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence

from my_agent_crew import texts_desktop_act as ta
from my_agent_crew.desktop.browsers import BUNDLE_IDS, NAMES

SPOTLIGHT_NAME, SPOTLIGHT_BUNDLE = "Spotlight", "com.apple.Spotlight"
# The control characters but tab and the two line breaks. None of them draws, and each one
# reaches an application as a key: a backspace typed in the middle of a word changes the word
# a person approved into another, so no text holding one is typed or set (the helper refuses
# it too), and a name the screen gave is shown with each one written out.
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
# A frame id as the helper makes it: the pixels' hash, the picture's size, the display.
FRAME_ID = re.compile(r"[0-9a-f]{16}-[0-9]{1,10}x[0-9]{1,10}-[0-9]{1,10}")
# macOS finds a program whatever the case its name is typed in.
SUDO = re.compile(r"\bsudo\b", re.I)
RM = re.compile(r"\brm((?:[ \t]+-[-\w]+)+)", re.I)
FETCH = re.compile(r"(?<![\w.-])(?:curl|wget)(?![\w-])", re.I)
SUBSTITUTED = re.compile(r"(?:\$\(|<\(|`)\s*(?:curl|wget)(?![\w-])", re.I)
# A shell's name, a word that runs what follows as a shell would, or a lone dot.
RUNS = re.compile(
    r"(?<![\w.-])(?:(?:ba|z|da|k|fi|c|tc)?sh|eval|source|\$\{?shell\}?)(?![\w.-])"
    r"|(?<!\S)\.(?=\s)",
    re.I,
)
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "fish", "csh", "tcsh", "$shell"})
# Words a command line may put before the program it runs.
BEFORE = frozenset({"sudo", "exec", "env", "command", "nohup", "time", "nice", "xargs"})
ENDS = re.compile(r"[\n;&]+")
# A line carried on into the next, and what a shell takes out of a word before running it.
CARRIED = re.compile(r"\\\r?\n")
UNQUOTED = str.maketrans("", "", "'\"\\")
BRACKETS = str.maketrans("", "", "(){}")
# A pipe at the end of a line, which goes on into the next one.
PIPE_ENDS_LINE = re.compile(r"\|[ \t\r]*\n\s*")


def frame_size(frame_id: str) -> tuple[int, int]:
    """How wide and how high the picture a frame id names is: the space its points lie in."""
    width, height = frame_id.split("-")[1].split("x")
    return int(width), int(height)


def code_point(char: str) -> str:
    """A character as its code point is written: a backspace is U+0008."""
    return f"U+{ord(char):04X}"


def shown_controls(text: str) -> str:
    """The text with each control character written out as its code point, in brackets."""
    return CONTROL.sub(lambda found: f"[{code_point(found.group())}]", text)


def _folded(name: str) -> str:
    """A name as it reads: one letter written whole or as a letter and its mark is one."""
    return unicodedata.normalize("NFD", unicodedata.normalize("NFD", name).casefold())


BROWSER_NAMES = frozenset(_folded(name) for name in NAMES)


def is_browser(written: str) -> bool:
    """Whether a name or a bundle id is a web browser's. A name is one whatever its case and
    accents; a bundle id is a browser's, or one that goes on from it after a dot (a beta, or a
    site saved as an app), compared as the helper compares it: without regard to case."""
    text = written.strip()
    lowered = text.lower()
    return _folded(text) in BROWSER_NAMES or any(
        lowered == known.lower() or lowered.startswith(f"{known.lower()}.") for known in BUNDLE_IDS
    )


def app_allowed(apps: Sequence[str], name: str = "", bundle_id: str = "") -> bool:
    """Whether the agent's list names this application. A browser it never names."""
    if (name and is_browser(name)) or (bundle_id and is_browser(bundle_id)):
        return False
    folded = _folded(name)
    return any(
        (name and _folded(entry) == folded) or (bundle_id and entry == bundle_id) for entry in apps
    )


def app_named(apps: Sequence[str], written: str) -> bool:
    """Whether what a call wrote for an application, a name or a bundle id, is in the list."""
    return app_allowed(apps, written, written)


def spotlight_allowed(apps: Sequence[str]) -> bool:
    return app_allowed(apps, SPOTLIGHT_NAME, SPOTLIGHT_BUNDLE)


def _removes_all(flags: str) -> bool:
    """Whether the flags after an `rm` say both to go into folders and not to ask."""
    words = flags.split()
    if "--" in words:  # what follows it is a name, however it is written
        words = words[: words.index("--")]
    short = "".join(word[1:] for word in words if not word.startswith("--"))
    long = {word.lower() for word in words if word.startswith("--")}
    recursive = "r" in short.lower() or "--recursive" in long
    return recursive and ("f" in short or "--force" in long)


def _runs_shell(stage: str) -> bool:
    """Whether a stage of a pipe runs a shell: its first word that is not one a line puts
    before a program, an option, a setting or a number, out of any brackets."""
    for word in stage.translate(BRACKETS).split():
        name = word.rsplit("/", 1)[-1].lower()
        if name in BEFORE or name.startswith("-") or "=" in name or name.isdigit():
            continue
        return name in SHELLS
    return False


def _fetched_into_shell(text: str) -> bool:
    """A download handed to a shell: piped into one, or run as what a shell is given. Each
    stage of a pipe is looked at once, however many of them download."""
    piped = PIPE_ENDS_LINE.sub("| ", text.replace("|&", "|"))
    for line in ENDS.split(piped):
        stages = line.split("|")
        first = next((at for at, stage in enumerate(stages) if FETCH.search(stage)), None)
        if first is not None and any(_runs_shell(later) for later in stages[first + 1 :]):
            return True
    for line in text.splitlines():
        runs = RUNS.search(line)
        if runs and SUBSTITUTED.search(line, runs.end()):
            return True
    return False


def typed_refusal(text: str) -> str:
    """The sentence a text is refused with before anyone is asked, or ""."""
    read = CARRIED.sub("", text).translate(UNQUOTED)
    if SUDO.search(read):
        return ta.ACT_TEXT_SUDO
    if any(_removes_all(found.group(1)) for found in RM.finditer(read)):
        return ta.ACT_TEXT_RM
    if _fetched_into_shell(read):
        return ta.ACT_TEXT_PIPE
    return ""
