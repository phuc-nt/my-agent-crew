"""What an agent can do right now, and how that is told to an agent that hands work out.

A roster line used to carry only the description its owner wrote, so an agent given a new
server, skill, job or tool stayed unknown to the master until someone remembered to rewrite
that line. What is here is filled from the running crew each time a prompt is built
(`server/crew_abilities.py`): nobody has to remember anything, and it cannot go stale.

A set of names is told against the reader's own where that is the shorter way to say it
("như của bạn, thêm: …"); one that differs too much to be read that way is listed whole.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from my_agent_crew import texts

READ_WRITE, READ_ONLY, SIGNED_OUT, DOWN = "read_write", "read_only", "signed_out", "down"
STANDINGS = {
    READ_WRITE: texts.CREW_SERVICE_READ_WRITE,
    READ_ONLY: texts.CREW_SERVICE_READ_ONLY,
    SIGNED_OUT: texts.CREW_SERVICE_SIGNED_OUT,
    DOWN: texts.CREW_SERVICE_DOWN,
}
# A skill or a server is one item of a line here, not a paragraph.
DESCRIPTION_CHARS = 80


@dataclass(frozen=True)
class Service:
    """An MCP server an agent's profile names, and how far the agent reaches it now."""

    name: str
    standing: str
    description: str = ""


@dataclass(frozen=True)
class Abilities:
    # Its own tools by name. `delegate` is not one of them, since a turn that was handed
    # work never holds it; nor are the tools of MCP servers, which `services` stands for.
    tools: tuple[str, ...] = ()
    # (name, description) of every skill the agent can read.
    skills: tuple[tuple[str, str], ...] = ()
    services: tuple[Service, ...] = ()
    # The jobs it runs on a schedule that are switched on, by name.
    jobs: tuple[str, ...] = ()
    model: str = ""
    # The model a stuck turn of it moves to, when it has one.
    escalation: str = ""


def _short(text: str) -> str:
    line = " ".join(text.split())
    if len(line) <= DESCRIPTION_CHARS:
        return line
    return line[: DESCRIPTION_CHARS - 1].rstrip() + "…"


def told_against(
    theirs: Sequence[str],
    mine: Sequence[str] | None,
    label: Callable[[str], str] = str,
) -> str:
    """`theirs` as one line. Against `mine` when the names that differ are at most half as
    many as the names there are to list; whole otherwise, or when there is no reader to
    compare with. Empty when there is nothing to tell."""
    if mine is not None:
        own, held = set(mine), set(theirs)
        extra = [name for name in theirs if name not in own]
        missing = [name for name in mine if name not in held]
        if theirs and 2 * (len(extra) + len(missing)) <= len(theirs):
            differs = []
            if extra:
                differs.append(texts.CREW_NAMES_EXTRA.format(names=", ".join(map(label, extra))))
            if missing:
                differs.append(texts.CREW_NAMES_MISSING.format(names=", ".join(missing)))
            same = texts.CREW_NAMES_SAME
            return f"{same}, {'; '.join(differs)}" if differs else same
    return ", ".join(label(name) for name in theirs)


def _service(service: Service) -> str:
    said = texts.CREW_SERVICE.format(name=service.name, standing=STANDINGS[service.standing])
    about = _short(service.description)
    return texts.CREW_SERVICE_ABOUT.format(service=said, description=about) if about else said


def ability_lines(theirs: Abilities, mine: Abilities | None = None) -> list[str]:
    """What `theirs` holds, a line for each kind of thing; a kind it has none of is left
    out. `mine` is the agent being told, whose own tools and skills need no explaining."""
    own_skills = {name for name, _ in mine.skills} if mine else set()
    about = {name: _short(description) for name, description in theirs.skills}

    def skill(name: str) -> str:
        # A skill the reader holds too is already in its own index, described.
        if name in own_skills or not about[name]:
            return name
        return texts.CREW_SKILL_ABOUT.format(name=name, description=about[name])

    model = theirs.model
    if model and theirs.escalation:
        model = texts.CREW_MODEL_ESCALATES.format(model=model, escalation=theirs.escalation)
    kinds = [
        (texts.CREW_SERVICES, "; ".join(_service(service) for service in theirs.services)),
        (
            texts.CREW_SKILLS,
            told_against(
                [name for name, _ in theirs.skills],
                [name for name, _ in mine.skills] if mine else None,
                skill,
            ),
        ),
        (texts.CREW_JOBS, ", ".join(theirs.jobs)),
        (texts.CREW_TOOLS, told_against(theirs.tools, mine.tools if mine else None)),
        (texts.CREW_MODEL, model),
    ]
    return [texts.CREW_ABILITY_LINE.format(kind=kind, held=held) for kind, held in kinds if held]
