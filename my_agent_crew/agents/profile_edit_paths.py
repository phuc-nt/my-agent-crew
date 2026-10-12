"""Where an edit from the web may point an agent.

A profile read from a file may point anywhere — a kit names its markdown by absolute
path, and `agent add --workspace` aims an agent at a repo elsewhere on purpose. An edit
arriving over HTTP is not that: whoever reaches this port would otherwise pick any
readable file as a persona (its text goes to the model on the next turn) or aim the
workspace tools at the source tree. So the checks live here, on the edit path, rather
than in the parser both of those share, and are about what the edit brings: a path the
agent already runs with stays where it is.

Two things are judged, because the file keeps a path as the text that was sent and the
text is followed again at every start: where it leads today (`check_inside_home`), and
whether it would still lead there tomorrow (`check_spelling`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from my_agent_crew import texts
from my_agent_crew.agents.profile import PERSONA_FILES, AgentProfile

# Keys naming a path on disk, and each a kind of its own: one never vouches for another.
PATH_KEYS = ("persona_files", "skills_dirs", "workspace")


def check_inside_home(
    profile: AgentProfile, home: Path, before: AgentProfile | None = None
) -> None:
    """Every path an edit brings has to stay under the crew home.

    `before` is the agent as it runs now. A path it already runs with is not the edit's:
    the file was written by hand to point there, and a save that leaves it where it is
    gives whoever reaches this port nothing new. Each kind is measured against its own
    kind and no other, so a workspace elsewhere makes neither that folder a place skills
    are loaded from nor a file under it a persona. A new agent has none: all it names is
    the edit's.
    """
    home = home.resolve()
    held = _paths(before) if before else ((), (), ())
    for brought, kept in zip(_paths(profile), held, strict=True):
        known = {path.resolve() for path in kept}
        for path in brought:
            resolved = path.resolve()
            if not resolved.is_relative_to(home) and resolved not in known:
                raise ValueError(texts.PATH_OUTSIDE_HOME.format(path=str(path)))


def _paths(profile: AgentProfile) -> tuple[Sequence[Path], ...]:
    """A profile's paths, a kind at a time: the workspace, skills folders, persona files."""
    personas = [profile.dir / name for name in profile.persona_files]
    return (profile.workspace,), profile.skills_dirs, personas


def check_spelling(
    agent_dir: Path, home: Path, held: Mapping[str, Any], to_be: Mapping[str, Any]
) -> None:
    """A path the home does not hold is spelled as the file spells it today, or as it is.

    `check_inside_home` has found that every path leads into the home or to a place the
    agent runs with. That is true of where the text leads now. A text that gets there
    through a link, or by going into a folder and back out with `..`, leads there only
    until the link or the folder is moved, and an agent with a shell can move either: the
    next start would then follow the saved text to a place no edit was ever judged for. So
    a text is taken when the home holds it (`_inside`), when the file already holds it for
    the same kind of path (the owner's own, and the save writes nothing new), or when it
    is the path itself with nothing left to follow. Any other is refused with the path to
    write in its place; none is rewritten on the person's behalf.

    `held` and `to_be` are the file as the start reads it now and as it will read the
    save. A key the edit does not name is spelled the same in both, so it is never the
    edit's; one the edit takes out is spelled by the name the start falls back on. Only a
    text the edit brings is followed here, and the parser has followed each already.
    """
    home = home.resolve()
    for kept, brought, tilde in zip(_spelled(held), _spelled(to_be), _READS_TILDE, strict=True):
        for text in brought:
            if text in kept:
                continue
            followed = agent_dir / (Path(text).expanduser() if tilde else Path(text))
            real = followed.resolve()
            if _inside(followed, real, home) or followed == real:
                continue
            raise ValueError(texts.PATH_SPELLED_ANEW.format(path=text, real=str(real)))


def _inside(followed: Path, real: Path, home: Path) -> bool:
    """Whether the home holds a path both as it is written and as it leads.

    Where it leads is not enough. A link lying in a tree outside the home leads into the
    home only until whoever works in that tree points it elsewhere, and the next start
    follows the saved text there. So the text counts too, made absolute with nothing
    followed: `~` read, joined to the agent's folder, `.` and `..` folded as text."""
    written = Path(os.path.normpath(followed))
    return written.is_relative_to(home) and real.is_relative_to(home)


# Whether the start reads `~` in a text of each kind, in the order `_spelled` gives them: a
# persona's name is joined to the agent's folder as it stands.
_READS_TILDE = (True, True, False)


def _spelled(raw: Mapping[str, Any]) -> tuple[Sequence[str], ...]:
    """A manifest's paths as it spells them, a kind at a time: the workspace, skills
    folders, persona files. What a file leaves out is spelled by the name `parse_profile`
    reads in its place, and the agent's own `skills` folder is read whatever the file says."""
    workspace = str(raw.get("workspace") or "workspace")
    skills = ["skills", *_texts(raw.get("skills_dirs"))]
    personas = _texts(raw.get("persona_files")) or PERSONA_FILES
    return (workspace,), skills, personas


def _texts(value: Any) -> list[str]:
    """A list's entries as the start goes through them. A value there is no going through
    spells no path. The start refuses a file that holds one, so this is a file a hand has
    changed under an agent that runs, met by the edit that takes the value out."""
    try:
        return [str(entry) for entry in value or ()]
    except TypeError:
        return []
