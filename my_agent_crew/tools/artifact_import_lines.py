"""What `artifact_import` answers with: the title a file gives its canvas, and the lines of a
result. A result names the file, its size and a digest, and counts what a page points at; it
never quotes the file, so whoever wrote the file puts no words into what a model reads back."""

from __future__ import annotations

import unicodedata
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from my_agent_crew.artifacts.kinds import BINARY_KINDS, TITLE_MAX
from my_agent_crew.tools.artifact_context import kind_label
from my_agent_crew.tools.artifact_file_texts import (
    IMPORT_RELATIVE_REFS,
    IMPORT_SOURCE,
    IMPORT_SOURCE_READABLE,
)

if TYPE_CHECKING:
    from my_agent_crew.store.artifact_models import ArtifactSummary
    from my_agent_crew.tools.artifact_source import SourceFile

# Enough of the sha256 to tell two files apart at a glance.
DIGEST_SHOWN = 12


def default_title(relative: str) -> str:
    """The file's name without its suffix; for an index page, the folder it sits in when it
    sits in one. Composed before it is cut, so the cut falls between whole letters."""
    path = PurePosixPath(relative)
    name = path.parent.name if path.stem == "index" and path.parent.name else path.stem
    return unicodedata.normalize("NFC", name)[:TITLE_MAX]


def imported_line(
    template: str, relative: str, summary: ArtifactSummary, file: SourceFile, **more: int
) -> str:
    """`template` filled in for `file`, now the newest version of the canvas `summary`."""
    return template.format(
        path=relative,
        title=summary.title,
        kind=kind_label(summary),
        size=file.size,
        digest=file.digest[:DIGEST_SHOWN],
        **more,
    )


def source_lines(kind: str, shown: str, refs: int) -> list[str]:
    """Where the canvas came from and, for a page, how many files it will not find. Only the
    count: an example would be text of the file's own choosing. A picture is not offered for
    reading, which `artifact_read` would refuse."""
    line = IMPORT_SOURCE if kind in BINARY_KINDS else IMPORT_SOURCE_READABLE
    warning = [IMPORT_RELATIVE_REFS.format(count=refs)] if refs else []
    return [line.format(source=shown), *warning]
