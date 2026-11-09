"""Where a file the person hands an agent lands: `<workspace>/inbox/<timestamp>-<name>`.

Telegram saves a photo or a document there, and so does the web composer. The agent reads
the saved path in the message (`TELEGRAM_ATTACHMENT_LINE`) and takes it from there:
`image_read` looks at a picture, a script or a `cp` moves a paper on."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

INBOX_DIR = "inbox"
_UNSAFE = re.compile(r"[^\w.\-]+")


def inbox_file(inbox: Path, name: str, fallback: str, now: datetime) -> Path:
    """The timestamp keeps two photos from one minute apart; the name is the sender's when
    there is one, else `fallback`. Both are reduced to a plain file name, so a crafted name
    cannot leave the inbox."""
    plain = _UNSAFE.sub("_", Path(name).name).strip("._")
    return inbox / f"{now:%Y%m%d-%H%M%S}-{plain or fallback}"


def free_path(path: Path) -> Path:
    """`path`, or `name-2.ext`, `name-3.ext`… when a file already sits there: two pictures
    pasted in the same second must not overwrite each other."""
    candidate, n = path, 1
    while candidate.exists():
        n += 1
        candidate = path.with_name(f"{path.stem}-{n}{path.suffix}")
    return candidate
