"""How a canvas names where it came from: `workspace:<agent id>/<path>` for a file in an
agent's workspace, or a plain web link to the original. Both are shown to a person and quoted
to a model, so neither may carry a character that hides, reorders or ends the line it sits on;
the checks run before a file is read, and again on the name found on disk."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

from my_agent_crew.agent_ids import is_agent_id
from my_agent_crew.tools.artifact_file_texts import IMPORT_BAD_PATH, IMPORT_BAD_URL
from my_agent_crew.tools.registry import ToolError

PATH_MAX = 1024
URL_MAX = 2000
WORKSPACE_PREFIX = "workspace:"
# Control and format characters and the two Unicode line breaks: none shows where it stands.
_HIDDEN = ("Cc", "Cf", "Zl", "Zp")
_REF = re.compile(r"""\b(?:src|href)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""", re.IGNORECASE)
# What a canvas can show without loading a file that sits beside the page.
_NOT_A_FILE = ("data:", "blob:", "http:", "https:", "//", "#", "mailto:", "javascript:")


def _hides(text: str) -> bool:
    return any(unicodedata.category(ch) in _HIDDEN for ch in text)


def check_path(relative: str) -> str:
    """`relative` as sent, when it is a path that can be shown and stored as it is."""
    if not relative.strip() or len(relative) > PATH_MAX or _hides(relative):
        raise ToolError(IMPORT_BAD_PATH.format(limit=PATH_MAX))
    return relative


def workspace_path(root: Path, path: Path) -> str:
    """`path`, a file under the workspace `root`, as it is kept and shown: counted from the
    root, never from the top of this machine. The path sent was checked, but this is the name
    found on disk, so it is checked too."""
    return check_path(path.relative_to(root.resolve()).as_posix())


def source_for(agent_id: str, root: Path, path: Path) -> str:
    """The source naming `path`, a file under the workspace `root` of `agent_id`."""
    return f"{WORKSPACE_PREFIX}{agent_id}/{workspace_path(root, path)}"


def parse_source(source: str) -> tuple[str, str] | None:
    """The agent id and the path a workspace source names; None for a link, for no source and
    for anything else. Cut at the first slash: an agent id holds none, a path may hold any."""
    if not source.startswith(WORKSPACE_PREFIX):
        return None
    agent_id, _, path = source.removeprefix(WORKSPACE_PREFIX).partition("/")
    return (agent_id, path) if path and is_agent_id(agent_id) else None


def web_url(value: str) -> str:
    """`value` as sent, when it is a plain http or https link to a named host."""
    refusal = ToolError(IMPORT_BAD_URL.format(limit=URL_MAX))
    if len(value) > URL_MAX or _hides(value) or any(ch.isspace() for ch in value):
        raise refusal
    try:
        parts = urlsplit(value)
        host = parts.hostname
    except ValueError:
        raise refusal from None
    if parts.scheme not in ("http", "https") or not host:
        raise refusal
    return value


def relative_ref_count(text: str) -> int:
    """How many different files a page points at with `src=` or `href=` and no scheme: the
    ones a canvas, which loads nothing from beside the page, will not show."""
    values = {(a or b or c).strip() for a, b, c in _REF.findall(text)}
    return sum(1 for value in values if value and not value.lower().startswith(_NOT_A_FILE))
