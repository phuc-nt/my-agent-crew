"""Server start-up loads only what every session needs. The PDF libraries take a
noticeable slice of it and most sessions never open a PDF, so they load on first use."""

import subprocess
import sys

PROBE = """
import sys
import my_agent_crew.server.app
import my_agent_crew.tools.pdf
print(sorted(m for m in sys.modules if m in ("pypdf", "pypdfium2")))
"""


def test_pdf_libraries_are_not_imported_until_a_pdf_is_read():
    result = subprocess.run(
        [sys.executable, "-c", PROBE], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]"
