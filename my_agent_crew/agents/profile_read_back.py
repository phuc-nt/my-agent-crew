"""A look at the file a save is about to write, as the next start will read it.

`agent.yaml` is written by one library and read at the start by another, and the two go by
two versions of YAML. Where they disagree about what the writer wrote, the save answers that
it worked, and the next start reads another profile, or refuses the file and does not come
up. The writer is kept from every such text that is known (`profile_write.py`). This is for
the one that is not: nothing is wired and nothing is written unless the file to be, read as
the start reads it, is the file as the start reads it now with the edit's keys set.

Both sides of that are read by the start's own reader. A value a person wrote by hand that
the two libraries read differently is then the same on both, and holds up no save.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml as boot_reader

from my_agent_crew import texts
from my_agent_crew.agents.profile_edit import apply_patch
from my_agent_crew.agents.profile_write import as_text


def read_now(manifest: Path) -> dict[str, Any]:
    """The file as the start reads it today. A new agent has none: nothing is held."""
    try:
        now = boot_reader.safe_load(manifest.read_text("utf-8")) if manifest.is_file() else None
    except boot_reader.YAMLError as exc:
        raise ValueError(texts.MANIFEST_BROKEN.format(error=str(exc))) from exc
    return now if isinstance(now, dict) else {}


def read_to_be(raw: Any) -> dict[str, Any]:
    """The file a save is about to write, as the next start will read it. `raw` is the
    manifest with the edit applied."""
    try:
        return boot_reader.safe_load(as_text(raw)) or {}
    except boot_reader.YAMLError as exc:
        raise ValueError(texts.SAVE_READS_BACK_CHANGED.format(what=str(exc))) from exc


def check_read_back(manifest: Path, raw: Any, patch: Mapping[str, Any]) -> None:
    """A ValueError saying what of the file would be read as something the edit did not
    ask for. `raw` is the manifest with the edit applied, as it is about to be written."""
    asked = apply_patch(read_now(manifest), dict(patch))
    written = read_to_be(raw)
    changed = sorted(
        str(key) for key in asked.keys() | written.keys() if asked.get(key) != written.get(key)
    )
    if changed:
        raise ValueError(texts.SAVE_READS_BACK_CHANGED.format(what=", ".join(changed)))
