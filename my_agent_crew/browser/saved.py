"""Where a browser tool leaves a file in the agent's workspace, and under what name.

The folder is the tool's own: neither the model nor a page chooses it. A name may come from
the model or from the site that sent the file, and either way only its plain letters are
kept, so no name leads out of the folder, hides the file, or reads as anything but a name.
A file is made new or not at all: nothing already in the folder is ever written over."""

from __future__ import annotations

import itertools
import os
import re
import shutil
from collections.abc import Sequence
from pathlib import Path

from my_agent_crew.browser.policy import plain
from my_agent_crew.texts import WORKSPACE_ESCAPE, WORKSPACE_WRITE_OUTSIDE
from my_agent_crew.tools.registry import ToolError

STEM_CHARS, ENDING_CHARS = 80, 10
PARTS = re.compile(r"[/\\]")
NOT_NAME = re.compile(r"[^A-Za-z0-9._]+")
EDGES = ".-_"


def place(workspace: Path, write_paths: Sequence[str], name: str) -> tuple[Path, str]:
    """The folder a tool's files go in, and that folder as the answer names it. An agent held
    to some folders keeps them under the first of those: what a browser signed in as its
    owner brings back is personal data, and the rule that keeps such an agent's files out of
    the rest of a git repo holds for the files of these tools too. The folder is judged where
    it really is, so one that a link leads out of the workspace, or out of those folders,
    takes no file."""
    base = Path(os.path.realpath(workspace))
    held = [Path(os.path.realpath(base / path)) for path in write_paths]
    folder = Path(os.path.realpath((held[0] if held else base) / name))
    if not folder.is_relative_to(base):
        raise ToolError(WORKSPACE_ESCAPE)
    if held and not any(folder.is_relative_to(path) for path in held):
        asked, paths = f"{write_paths[0]}/{name}", ", ".join(write_paths)
        raise ToolError(WORKSPACE_WRITE_OUTSIDE.format(paths=paths, path=asked))
    return folder, folder.relative_to(base).as_posix()


def file_name(said: str, fallback: str, ending: str = "") -> str:
    """A file name out of what the model or a site called the file: the last part of a path,
    its accents taken off, one hyphen for each run of anything that is no plain letter,
    digit, dot or underscore, and neither a dot nor a hyphen in front. `ending` is what the
    name must end in whatever was said; without one a name keeps the short ending it has, and
    a long tail after its last dot is part of the name. `fallback` stands for a name none of
    whose letters could be kept, before the ending it had."""
    last = PARTS.split(said.strip())[-1].replace("Đ", "D")
    bare = NOT_NAME.sub("-", plain(last))
    stem, dot, own = bare.rpartition(".")
    own = own.strip(EDGES)
    kept = own.casefold() == ending.casefold() if ending else 0 < len(own) <= ENDING_CHARS
    if not dot or not kept:
        stem, own = bare, ""
    stem = stem.strip(EDGES)[:STEM_CHARS].rstrip(EDGES) or fallback
    own = ending or own
    return f"{stem}.{own}" if own else stem


def keep(folder: Path, name: str, content: bytes | Path) -> Path:
    """Put `content` (the bytes, or the file that holds them) in the folder under `name`, or
    under that name with a number when it is taken. Made new or not at all: never over a
    file, nor through a link, already there; and a file that could not be written whole is
    taken away again."""
    folder.mkdir(parents=True, exist_ok=True)
    stem, dot, ending = name.rpartition(".")
    if not dot:
        stem, ending = name, ""
    for n in itertools.count(1):
        path = folder / f"{stem}{f'-{n}' if n > 1 else ''}{dot}{ending}"
        try:
            file = open(path, "xb")  # ours to take away again only once this did not raise
        except FileExistsError:
            continue
        try:
            with file:
                if isinstance(content, bytes):
                    file.write(content)
                else:
                    with open(content, "rb") as source:
                        shutil.copyfileobj(source, file)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return path
    raise AssertionError("unreachable")
