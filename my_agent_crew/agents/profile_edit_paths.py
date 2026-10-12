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
    """A path outside the home is spelled as the file spells it today, or as it is.

    `check_inside_home` has found that every such path is one the agent runs with. That
    is true of where the text leads now. A text that gets there through a link, or by
    going into a folder and back out with `..`, leads there only until the link or the
    folder is moved, and an agent with a shell can move either: the next start would then
    follow the saved text to a place no edit was ever judged for. So a text is taken when
    the file already holds it for the same kind of path (the owner's own, and the save
    writes nothing new), or when it is the path itself with nothing left to follow. Any
    other is refused with the path to write in its place; none is rewritten on the
    person's behalf.

    `held` and `to_be` are the file as the start reads it now and as it will read the
    save. A key the edit does not name is spelled the same in both, so it is never the
    edit's; one the edit takes out is spelled by the name the start falls back on.
    """
    home = home.resolve()
    for kept, brought in zip(_spelled(agent_dir, held), _spelled(agent_dir, to_be), strict=True):
        for text, followed in brought.items():
            real = followed.resolve()
            if text in kept or real.is_relative_to(home) or followed == real:
                continue
            raise ValueError(texts.PATH_SPELLED_ANEW.format(path=text, real=str(real)))


def _spelled(agent_dir: Path, raw: Mapping[str, Any]) -> tuple[dict[str, Path], ...]:
    """A manifest's paths as it spells them, each with the path the start follows for it,
    a kind at a time. What a file leaves out is spelled by the name `parse_profile` reads
    in its place, and the agent's own `skills` folder is read whatever the file says."""

    def followed(text: str) -> Path:
        return agent_dir / Path(text).expanduser()

    workspace = str(raw.get("workspace") or "workspace")
    skills = ["skills", *(str(folder) for folder in raw.get("skills_dirs") or [])]
    personas = [str(name) for name in raw.get("persona_files") or PERSONA_FILES]
    return (
        {workspace: followed(workspace)},
        {text: followed(text) for text in skills},
        # A persona's name is joined to the folder as it stands: no `~` is read in it.
        {name: agent_dir / name for name in personas},
    )
