"""How a reply names a file to send: the two line prefixes, the size a chat will take, and
the way a line names a canvas instead of a file in the workspace.

Shared by the channels that deliver a reply and the delegate tool that carries a child's
attachments over to its parent, so it lives outside both packages."""

from __future__ import annotations

import re

MEDIA_PREFIX = "MEDIA:"
FILE_PREFIX = "FILE:"
# Opens the path of an attachment line that names a canvas by its id.
ARTIFACT_REF = "artifact:"
_ARTIFACT_ID = re.compile(r"[0-9a-f]{12}")

# Telegram refuses a document over 50 MB, but the cap here is lower on purpose: it is a
# chat, and a file this size is one a person would rather fetch from the workspace page
# than receive twice on a phone.
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024


def reply_lines(text: str) -> list[str]:
    """The lines of a reply, cut at every line break a string knows. The channel that sends a
    reply and the relay that carries a child's answer to its parent both read lines here: a
    line one of them took for an attachment and the other for prose would get past the checks
    of the one that missed it."""
    return text.splitlines()


def artifact_ref(path: str) -> str | None:
    """The id of the canvas `path` names; None when it is a file path. A path that opens as a
    canvas and goes on as anything but one whole id is "": the line meant a canvas, so it is
    never looked up as a file, and it names none."""
    if not path.startswith(ARTIFACT_REF):
        return None
    artifact_id = path.removeprefix(ARTIFACT_REF).strip()
    return artifact_id if _ARTIFACT_ID.fullmatch(artifact_id) else ""
