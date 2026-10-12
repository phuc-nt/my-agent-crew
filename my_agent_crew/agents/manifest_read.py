"""Reading one `agent.yaml` the way the start reads it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from my_agent_crew import texts


def read_manifest(manifest: Path) -> Any:
    """What the file states. One that does not parse is a ValueError that says which file:
    the reader's own error names a line and a column, and a home holds one such file for
    every agent. As a ValueError it is refused wherever a profile of the wrong shape is;
    the reader's own error went past all of those as a traceback."""
    try:
        return yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(texts.MANIFEST_BROKEN.format(error=f"{manifest}: {exc}")) from exc
