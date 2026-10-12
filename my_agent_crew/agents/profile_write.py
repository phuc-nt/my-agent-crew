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
from io import StringIO
from pathlib import Path
from typing import Any

import yaml as boot_reader
from ruamel.yaml import YAML
from ruamel.yaml.representer import RoundTripRepresenter
from ruamel.yaml.scalarfloat import ScalarFloat
from ruamel.yaml.scalarstring import DoubleQuotedScalarString, LiteralScalarString

from my_agent_crew import texts

TRASH_DIR = ".trash"
MANIFEST = "agent.yaml"
# Wider than any file: no line of one is folded. A long text in quotes, broken where a
# line would end, was read back with a space it never had. A script's indented line
# became another line, and the next start refused the file for it.
NEVER_FOLDED = 2**20
# Two numbers laid out alike are one text once every digit is the same digit.
_ANY_DIGIT = str.maketrans("123456789", "000000000")


class _Written(RoundTripRepresenter):
    """How a number is put into the file: as one the next start reads, and the same one."""

    def represent_float(self, data: float) -> Any:
        """A number an edit brings. The library shows it as Python does: `1e-05`, `1e+16`.
        To the reader the server starts with, a float has a dot in it, and these are texts.
        With `.0` before the exponent both read the float that was saved."""
        node = super().represent_float(data)
        if "e" in node.value and "." not in node.value:
            node.value = node.value.replace("e", ".0e", 1)
        return node

    def represent_scalar_float(self, data: ScalarFloat) -> Any:
        """A number the file already holds, which the library writes back in the form it
        found it in, so that what a person typed stays typed. It cuts a long mantissa
        where it should round, and what it writes is then another number
        (`1.989032661366619e+244` came back ending in 8), or the same number in other
        digits. Its text is kept when it reads as the number and is not such a cut of
        the text an edit's number is given; otherwise that text is written."""
        node = super().represent_scalar_float(data)
        plain = self.represent_float(float(data)).value
        # `.inf` is no number to read, and is laid out as itself: it is asked nothing.
        cut = node.value.translate(_ANY_DIGIT) == plain.translate(_ANY_DIGIT)
        if cut or float(node.value) != data:
            node.value = plain
        return node


_Written.add_representer(float, _Written.represent_float)
_Written.add_representer(ScalarFloat, _Written.represent_scalar_float)


def _yaml() -> YAML:
    yaml = YAML()
    yaml.Representer = _Written
    yaml.preserve_quotes = True
    # Lists indent under their key rather than hanging at the parent's column, which is
    # how the bundled profiles are written and how people write them by hand.
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = NEVER_FOLDED
    return yaml


def as_written(value: Any) -> Any:
    """What a save brings, as a person would have written it by hand: a text of several
    lines is a block (`script: |`), not one long line with `\\n` in it. A script is read by
    its lines, and so is a prompt.

    A block holds what prints and the ends of its lines, and nothing else. A text with a
    tab, a carriage return or another alphabet's line separator in it would come back
    changed, or leave a file that no longer parses, so it is written in quotes as before.

    The writer goes by a later YAML than the reader the server starts with. A text it
    would leave bare may be no text to that reader (`No` a false, `1:30` a number), or
    another text (a bare U+0085 the end of a line). Such a one is put in quotes, where
    both read the text that was saved."""
    if isinstance(value, dict):
        return {key: as_written(item) for key, item in value.items()}
    if isinstance(value, list):
        return [as_written(item) for item in value]
    if type(value) is not str:
        return value
    if "\n" in value and all(char == "\n" or char.isprintable() for char in value):
        return LiteralScalarString(value)
    return value if _boots_as_itself(value) else DoubleQuotedScalarString(value)


def _boots_as_itself(text: str) -> bool:
    """Whether the text, left to the writer, is the text the next start reads."""
    try:
        return boot_reader.safe_load(as_text({"text": text})) == {"text": text}
    except boot_reader.YAMLError:
        return False


def as_text(data: Any) -> str:
    """The manifest as a save writes it."""
    written = StringIO()
    _yaml().dump(data, written)
    return written.getvalue()


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
    tmp.write_text(as_text(data), encoding="utf-8")
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
