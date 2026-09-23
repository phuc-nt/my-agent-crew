"""The secrets file beside the home's config: `<home>/env`, one `NAME=value` per line.

The launchd script sources it with `set -a; source env`, so whatever is written here is
read by a shell before it is read by Python. That is why a value is always written inside
single quotes and a value holding any control character or line separator is refused
outright: a line break in a key would otherwise become a second line of shell, run at the
next restart. The file is split on `\n` only, as the shell splits it — Python's
`splitlines` also breaks on form feeds and U+2028, which would let one shell line read as
two here, and a rewrite turn the second into a real one.

Only the lines for the name being changed are rewritten. Comments, blank lines and every
other entry stay byte for byte, so a file the person wrote by hand keeps its shape.
"""

from __future__ import annotations

import os
import re
import tempfile
import unicodedata
from collections.abc import MutableMapping
from pathlib import Path

ENV_FILE = "env"
NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
MAX_VALUE_CHARS = 4096
_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def env_path(home: Path) -> Path:
    return home / ENV_FILE


def _unquote(raw: str) -> str:
    """The value as `source` would see it, for the forms people actually write: bare,
    single-quoted (including the `'\\''` escape this module writes) and double-quoted.
    Anything cleverer (expansions, arrays) is read literally rather than guessed at."""
    raw = raw.strip()
    if raw.startswith("'"):
        parts = re.findall(r"'([^']*)'|\\(.)", raw)
        return "".join(quoted or escaped for quoted, escaped in parts)
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return re.sub(r'\\([\\"$`])', r"\1", raw[1:-1])
    # A bare value ends at the first unquoted space; what follows is a comment or noise.
    return raw.split(" ", 1)[0].split("\t", 1)[0]


def _quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _read_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").split("\n")
    return lines[:-1] if lines and lines[-1] == "" else lines


def read_env(path: Path) -> dict[str, str]:
    """Every `NAME=value` in the file, later lines winning like they do in a shell."""
    values: dict[str, str] = {}
    for line in _read_lines(path):
        if line.lstrip().startswith("#"):
            continue
        match = _LINE_RE.match(line)
        if match:
            values[match.group(1)] = _unquote(match.group(2))
    return values


def check_value(value: str) -> str:
    """The value to store, or ValueError. Trimmed, because a key pasted with a trailing
    newline is the most common way to end up with one that "looks right" and fails."""
    value = value.strip()
    if not value:
        raise ValueError("empty")
    if any(unicodedata.category(ch) in ("Cc", "Cs", "Zl", "Zp") for ch in value):
        raise ValueError("multiline")
    if len(value) > MAX_VALUE_CHARS:
        raise ValueError("too long")
    return value


def _write(path: Path, lines: list[str]) -> None:
    """Replace the file in one step, owner-only from the first byte: a crash mid-write
    leaves the old file, and there is no moment the secrets sit world-readable. A symlink
    (an env kept in a dotfiles repo) is followed, so the link stays a link."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".env-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("".join(f"{line}\n" for line in lines))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _lines_without(path: Path, name: str) -> tuple[list[str], int | None]:
    """The file's lines minus every assignment to `name`, and where the first one was."""
    lines = _read_lines(path)
    kept: list[str] = []
    first: int | None = None
    for line in lines:
        match = _LINE_RE.match(line)
        if match and match.group(1) == name and not line.lstrip().startswith("#"):
            first = len(kept) if first is None else first
            continue
        kept.append(line)
    return kept, first


def set_env(path: Path, name: str, value: str) -> None:
    """Write `name` in place of its old line, or at the end when it is new."""
    kept, first = _lines_without(path, name)
    line = f"{name}={_quote(value)}"
    if first is None:
        kept.append(line)
    else:
        kept.insert(first, line)
    _write(path, kept)


def remove_env(path: Path, name: str) -> bool:
    """Drop every assignment to `name`; False when there was none."""
    kept, first = _lines_without(path, name)
    if first is None:
        return False
    _write(path, kept)
    return True


def load_env_file(home: Path, environ: MutableMapping[str, str]) -> list[str]:
    """Put the file's entries into `environ` where the process did not already set them,
    so a server started without the launchd script still sees what the web saved. The
    process wins: a variable exported for one run is meant to override the file."""
    loaded = []
    for name, value in read_env(env_path(home)).items():
        if name not in environ:
            environ[name] = value
            loaded.append(name)
    return loaded
