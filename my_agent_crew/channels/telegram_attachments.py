"""Which lines of a reply are files rather than prose, and which files may be sent.

Two prefixes, because Telegram shows the two kinds differently and the model has to be
able to choose. `MEDIA:` is a photo, shown inline and re-encoded by Telegram, which is
what a chart wants and what a spreadsheet must never get. `FILE:` is a document, kept
byte for byte with its name, which is what a PDF or a CSV wants.

The extension list is a guard on the reply, not on the workspace. Anything the agent can
write it can also name on a `FILE:` line, so a reply is one sentence away from mailing out
a key file or an `.env` an earlier step happened to copy in. Naming the handful of formats
a person actually asks to receive costs a model nothing and closes that off; the workspace
guard next to it already refuses paths outside the agent's own directory.
"""

from __future__ import annotations

from pathlib import Path

MEDIA_PREFIX = "MEDIA:"
FILE_PREFIX = "FILE:"

# Telegram refuses a document over 50 MB, but the cap here is lower on purpose: it is a
# chat, and a file this size is one a person would rather fetch from the workspace page
# than receive twice on a phone.
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024

DOCUMENT_SUFFIXES = frozenset(
    {".pdf", ".csv", ".md", ".txt", ".xlsx", ".json", ".zip"},
)


def split_reply(text: str) -> tuple[str, list[str], list[str]]:
    """Splits the prose from the `MEDIA:` photos and the `FILE:` documents, each in the
    order the reply named them. A line is an attachment only when the prefix starts it,
    so a sentence mentioning the word in passing stays prose."""
    prose: list[str] = []
    media: list[str] = []
    files: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(MEDIA_PREFIX):
            media.append(stripped[len(MEDIA_PREFIX) :].strip())
        elif stripped.startswith(FILE_PREFIX):
            files.append(stripped[len(FILE_PREFIX) :].strip())
        else:
            prose.append(line)
    return "\n".join(prose).strip(), media, files


def document_suffix_allowed(relative: str) -> bool:
    """Case folded, since a reply naming `Brief.PDF` means the same file as `brief.pdf`."""
    return Path(relative).suffix.lower() in DOCUMENT_SUFFIXES


def allowed_suffix_list() -> str:
    """The formats, for the message that tells the model why its file was not sent. Sorted
    so the refusal reads the same every time rather than in set order."""
    return ", ".join(sorted(suffix.lstrip(".") for suffix in DOCUMENT_SUFFIXES))
