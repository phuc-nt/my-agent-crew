"""The browser tests run against the very policy and reporter the server sends. They read them
from two files, kept equal to their source here byte for byte. After changing either, write the
new text over its file: `render_csp()` into `render-policy.txt` (no newline at the end, the file
is a header value) and `REPORTER_JS` into `frame-reporter.js`."""

from __future__ import annotations

from pathlib import Path

from my_agent_crew.artifacts.render import REPORTER_JS, render_csp

E2E = Path(__file__).resolve().parents[1] / "web" / "e2e"


def _text(name: str) -> str:
    return (E2E / name).read_bytes().decode("utf-8")


def test_the_policy_the_browser_tests_use_is_the_one_the_server_sends():
    assert _text("render-policy.txt") == render_csp()


def test_the_reporter_the_browser_tests_use_is_the_one_every_html_page_carries():
    assert _text("frame-reporter.js") == REPORTER_JS
