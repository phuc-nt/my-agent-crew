"""Who wrote the versions of a canvas an agent has not seen, in one line: the tools say it
when they refuse a write or hand back a page, so the agent knows whose text it would meet."""

from __future__ import annotations

from collections.abc import Sequence

from my_agent_crew.store.artifact_models import RESTORE_NOTE, USER, ArtifactVersion
from my_agent_crew.texts_canvas import ARTIFACT_AUTHORS, AUTHOR_PERSON, AUTHOR_RESTORE

AUTHOR_GROUPS = 6


def authors_line(versions: Sequence[ArtifactVersion], after: int, upto: int) -> str:
    """Who wrote the versions numbered in (after, upto], from `versions` oldest first, one
    group per run of one author's versions and the newest six at most, since those are what
    the agent is about to meet; "" when there are none. A person's burst of saves folds into
    its last number, so a group spans the first and last number it holds rather than counting
    them. A restore is a group of its own: it brings back text the agent may already know."""
    groups: list[tuple[str, int, int]] = []
    for version in versions:
        if not after < version.version <= upto:
            continue
        name = AUTHOR_PERSON if version.author == USER else version.author
        restore = version.note.startswith(RESTORE_NOTE)
        if restore:
            restored = version.note.removeprefix(RESTORE_NOTE)
            name = AUTHOR_RESTORE.format(author=name, version=restored)
        if groups and groups[-1][0] == name and not restore:
            groups[-1] = (name, groups[-1][1], version.version)
        else:
            groups.append((name, version.version, version.version))
    if not groups:
        return ""
    named = [f"{_numbers(first, last)} {name}" for name, first, last in groups[-AUTHOR_GROUPS:]]
    if len(groups) > AUTHOR_GROUPS:
        named.insert(0, "…")
    return ARTIFACT_AUTHORS.format(groups=", ".join(named))


def _numbers(first: int, last: int) -> str:
    return f"v{first}" if first == last else f"v{first}–v{last}"
