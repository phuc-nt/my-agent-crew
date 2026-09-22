"""Writing `agent.yaml` back after someone edits an agent from the web.

Round-trip rather than dump: these files are hand-written, and a plain dump would
return them stripped of their comments, their key order and anything this version of
the code does not know about. What the person typed stays typed; an edit changes the
keys it names and leaves the rest of the file alone.

Removing an agent moves its directory aside instead of deleting it. A crew is a few
folders of hand-written text — undoing a misclick has to be possible.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from my_agent_crew import texts

TRASH_DIR = ".trash"
MANIFEST = "agent.yaml"


def _yaml() -> YAML:
    yaml = YAML()
    yaml.preserve_quotes = True
    # Lists indent under their key rather than hanging at the parent's column, which is
    # how the bundled profiles are written and how people write them by hand.
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


def read_raw(manifest: Path) -> Any:
    """The file as ruamel sees it — comments and key order attached. An absent or empty
    manifest reads as an empty mapping so a first edit has something to write into."""
    if not manifest.is_file():
        return _yaml().map()
    loaded = _yaml().load(manifest.read_text(encoding="utf-8"))
    if loaded is None:
        return _yaml().map()
    # A profile is a mapping of keys. A file holding a list or a bare scalar still parses
    # as YAML, and setting a key on it would fail deep inside the patch with a TypeError
    # that says nothing about which file is wrong.
    if not isinstance(loaded, dict):
        raise ValueError(texts.MANIFEST_NOT_A_MAPPING.format(path=str(manifest)))
    return loaded


def write_raw(manifest: Path, data: Any) -> None:
    """Replace the manifest in one step.

    Written to a sibling temp file and moved over the target: a crash halfway through a
    dump would otherwise leave a half-written profile that no longer parses, and the
    agent it describes would not come back after a restart.
    """
    manifest.parent.mkdir(parents=True, exist_ok=True)
    tmp = manifest.with_name(f".{manifest.name}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        _yaml().dump(data, handle)
    os.replace(tmp, manifest)


def agent_dir(home: Path, agent_id: str) -> Path:
    return home / "agents" / agent_id


def create_agent_dir(home: Path, agent_id: str) -> Path:
    """The folder a new agent lives in, with the places it will look for its own things.
    An agent with no workspace cannot run a single tool, so the directory is made now
    rather than on the first failure."""
    directory = agent_dir(home, agent_id)
    (directory / "workspace").mkdir(parents=True, exist_ok=True)
    return directory


def trash_agent(home: Path, agent_id: str) -> Path:
    """Move the agent's folder into `agents/.trash/<id>-<stamp>` and say where it went.

    Stamped because the same id can be created and removed repeatedly, and the second
    removal must not overwrite what the first one saved.
    """
    source = agent_dir(home, agent_id)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    trash = home / "agents" / TRASH_DIR
    trash.mkdir(parents=True, exist_ok=True)
    target = trash / f"{agent_id}-{stamp}"
    suffix = 1
    while target.exists():
        suffix += 1
        target = trash / f"{agent_id}-{stamp}-{suffix}"
    os.replace(source, target)
    return target
