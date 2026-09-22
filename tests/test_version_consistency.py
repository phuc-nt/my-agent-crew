"""One release is one number: the backend, the web bundle and the docs say the same thing.

Nothing at runtime reads all three, so they drift silently — a release can ship with
`pyproject.toml` at 0.4.0 and `web/package.json` still at 0.3.0 and every other test stays
green. This is the only thing that notices.
"""

import json
import re
import tomllib
from pathlib import Path

import my_agent_crew

ROOT = Path(__file__).resolve().parents[1]
DOC_VERSION = re.compile(r"^\*\*Phiên bản\*\*: (\S+)", re.MULTILINE)


def declared_version() -> str:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return pyproject["project"]["version"]


def test_package_and_web_agree_on_the_version():
    web = json.loads((ROOT / "web" / "package.json").read_text(encoding="utf-8"))
    assert my_agent_crew.__version__ == declared_version()
    assert web["version"] == declared_version()


def test_every_standard_doc_names_the_released_version():
    # The six standard docs carry a version line; a stale one sends a reader to the wrong
    # feature list. Reference docs (agents, tools, memory…) have no such line and are skipped.
    stale = {}
    for doc in sorted((ROOT / "docs").glob("*.md")):
        found = DOC_VERSION.search(doc.read_text(encoding="utf-8"))
        if found and found.group(1) != declared_version():
            stale[doc.name] = found.group(1)
    assert stale == {}


def test_the_changelog_has_an_entry_for_the_released_version():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{declared_version()}]" in changelog
