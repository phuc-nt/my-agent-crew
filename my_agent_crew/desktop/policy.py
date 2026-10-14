"""The rules of the desktop that read no helper: which applications are an agent's own, and
what is never typed into any of them.

An application is an agent's when the agent's list names it: by its name, whatever the
case, or by its bundle id, letter for letter. The text rules are hard refusals: they hold
for every agent and no setting turns them off. They are a tripwire for the plain spellings
and not a wall, since text can be typed in pieces; what an agent types is still a call a
person approves unless the conversation runs on its own.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from my_agent_crew import texts_desktop_act as ta

SPOTLIGHT_NAME, SPOTLIGHT_BUNDLE = "Spotlight", "com.apple.Spotlight"
# A frame id as the helper makes it: the pixels' hash, the picture's size, the display.
FRAME_ID = re.compile(r"[0-9a-f]{16}-[0-9]{1,10}x[0-9]{1,10}-[0-9]{1,10}")
# macOS finds a program whatever the case its name is typed in.
SUDO = re.compile(r"\bsudo\b", re.I)
RM = re.compile(r"\brm((?:[ \t]+-[-\w]+)+)", re.I)
FETCH = re.compile(r"(?<![\w.-])(?:curl|wget)(?![\w-])", re.I)
SUBSTITUTED = re.compile(r"(?:\$\(|<\(|`)\s*(?:curl|wget)(?![\w-])", re.I)
RUNS = re.compile(r"(?<![\w.-])(?:(?:ba|z|da|k|fi)?sh|eval|source)(?![\w.-])", re.I)
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "fish"})
# Words a command line may put before the program it runs.
BEFORE = frozenset({"sudo", "exec", "env", "command", "nohup", "time"})
ENDS = re.compile(r"[\n;&]+")


def frame_size(frame_id: str) -> tuple[int, int]:
    """How wide and how high the picture a frame id names is: the space its points lie in."""
    width, height = frame_id.split("-")[1].split("x")
    return int(width), int(height)


def app_allowed(apps: Sequence[str], name: str = "", bundle_id: str = "") -> bool:
    """Whether the agent's list names this application."""
    lowered = name.casefold()
    return any(
        (name and entry.casefold() == lowered) or (bundle_id and entry == bundle_id)
        for entry in apps
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
    words = stage.split()
    while words and (words[0].lower() in BEFORE or "=" in words[0]):
        words = words[1:]
    return bool(words) and words[0].rsplit("/", 1)[-1].lower() in SHELLS


def _fetched_into_shell(text: str) -> bool:
    """A download handed to a shell: piped into one, or run as what a shell is given."""
    for line in ENDS.split(text):
        stages = line.split("|")
        for at, stage in enumerate(stages[:-1]):
            if FETCH.search(stage) and any(_runs_shell(later) for later in stages[at + 1 :]):
                return True
    for line in text.splitlines():
        found = SUBSTITUTED.search(line)
        if found and RUNS.search(line[: found.start()]):
            return True
    return False


def typed_refusal(text: str) -> str:
    """The sentence a text is refused with before anyone is asked, or ""."""
    if SUDO.search(text):
        return ta.ACT_TEXT_SUDO
    if any(_removes_all(found.group(1)) for found in RM.finditer(text)):
        return ta.ACT_TEXT_RM
    if _fetched_into_shell(text):
        return ta.ACT_TEXT_PIPE
    return ""
