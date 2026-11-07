"""What a command job said about why it failed, read out of all it printed.

A command that fails rarely ends on the line that says why: a script logs `ERROR: …` and
then the JSON body of the refusal it got, so its last line is a lone `}` and the end of all
it printed opens in the middle of an id. Where a line says it reports an error (`ERROR:`,
`Lỗi:`, `ValueError:`, `… thất bại:`), what it said is that line and every line after it,
on one line; the last such line is the one kept, since an earlier one may be a retry that
went on. Where no line says so, nothing here is said and the caller keeps what it had.
"""

from __future__ import annotations

import re

# A word that says a line reports an error, followed by its colon. The colon is what tells
# `ERROR: delete failed` from the `"error": {` of the JSON body printed after it.
_REPORTS_ERROR = re.compile(r"(error|fail(?:ed|ure)?|lỗi|thất bại|that bai)\s*:", re.IGNORECASE)


def what_failed(output: str) -> str:
    """From the last line that reports an error to the end, on one line; or "" for none."""
    lines = output.splitlines()
    for at in range(len(lines) - 1, -1, -1):
        if _REPORTS_ERROR.search(lines[at]):
            return " ".join(" ".join(lines[at:]).split())
    return ""
