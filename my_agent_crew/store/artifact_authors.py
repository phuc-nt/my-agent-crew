"""Who wrote the versions of a canvas an agent has not seen, in one line: the tools say it
when they refuse a write or hand back a page, so the agent knows whose text it would meet."""

from __future__ import annotations

from collections.abc import Sequence

from my_agent_crew.store.artifact_models import USER, ArtifactVersion
from my_agent_crew.texts_canvas import ARTIFACT_AUTHORS, AUTHOR_PERSON

AUTHOR_GROUPS = 6


def authors_line(versions: Sequence[ArtifactVersion], after: int, upto: int) -> str:
    """Who wrote the versions numbered in (after, upto], from `versions` oldest first, one
    group per run of one author's versions; "" when there are none. A person's burst of
    saves folds into its last number, so a group spans the first and last number it holds
    rather than counting them."""
    groups: list[tuple[str, int, int]] = []
    for version in versions:
        if not after < version.version <= upto:
            continue
        name = AUTHOR_PERSON if version.author == USER else version.author
        if groups and groups[-1][0] == name:
            groups[-1] = (name, groups[-1][1], version.version)
        else:
            groups.append((name, version.version, version.version))
    if not groups:
        return ""
    named = [f"{_numbers(first, last)} {name}" for name, first, last in groups[:AUTHOR_GROUPS]]
    if len(groups) > AUTHOR_GROUPS:
        named.append("…")
    return ARTIFACT_AUTHORS.format(groups=", ".join(named))


def _numbers(first: int, last: int) -> str:
    return f"v{first}" if first == last else f"v{first}–v{last}"
