"""No web browser is ever an agent's application on the desktop: a page is the browser tools'
to read and act in. A browser is known here by its name or its bundle id, and the helper
knows it by the same bundle ids, read out of its Swift source so the two lists cannot part.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

from my_agent_crew.desktop.browsers import BUNDLE_IDS, NAMES
from my_agent_crew.desktop.policy import app_allowed, app_named, is_browser

SOURCE = (
    Path(__file__).resolve().parents[1] / "desktop-helper/Sources/DesktopHelperCore/Browsers.swift"
)
LITERAL = re.compile(r"static let bundleIDs: \[String\] = \[(.*?)\n    \]", re.S)
ENTRY = re.compile(r'^\s*"([^"\\]+)",\s*$', re.M)


def helper_bundle_ids() -> list[str]:
    """The bundle ids the helper refuses to act in, in the order its source lists them."""
    (body,) = LITERAL.findall(SOURCE.read_text(encoding="utf-8"))
    return ENTRY.findall(body)


def test_the_browsers_known_here_are_the_helpers_own() -> None:
    assert helper_bundle_ids() == list(BUNDLE_IDS)
    assert len(set(BUNDLE_IDS)) == len(BUNDLE_IDS) == 19


@pytest.mark.parametrize(
    "written",
    [
        "Safari",
        "safari",
        " SAFARI ",
        "Google Chrome",
        "google chrome",
        "Chrome",
        "Firefox",
        "Microsoft Edge",
        "Arc",
        "Brave Browser",
        "Tor Browser",
        "DuckDuckGo",
        unicodedata.normalize("NFD", "Opera GX"),
    ],
)
def test_a_browser_is_known_by_its_name_whatever_its_case(written) -> None:
    assert is_browser(written)


@pytest.mark.parametrize(
    "written",
    [
        *BUNDLE_IDS,
        "COM.APPLE.SAFARI",
        "com.google.chrome",
        # A site saved as an application of its own, a beta, a build of a browser.
        "com.google.Chrome.app.kjgfgldnnfoeklkmfkjfagphfepbbdan",
        "com.apple.Safari.WebApp.3F1C",
        "com.google.Chrome.beta",
        "com.operasoftware.Opera",
        "com.operasoftware.OperaGX",
        "org.mozilla.firefox.nightly",
    ],
)
def test_a_browser_is_known_by_its_bundle_id_or_one_that_goes_on_from_it(written) -> None:
    assert is_browser(written)


@pytest.mark.parametrize(
    "written",
    [
        "Notes",
        "TextEdit",
        "Safari 2",
        "Safari Notes",
        "com.apple.Notes",
        "com.apple.TextEdit",
        # Only an id that goes on after a dot is a browser's: these merely start alike.
        "com.apple.SafariNotes",
        "com.google.ChromeRemoteDesktop",
        "com.operasoftwareX",
        "com.apple",
        "",
    ],
)
def test_an_application_that_only_resembles_a_browser_is_none(written) -> None:
    assert not is_browser(written)


@pytest.mark.parametrize("browser", ["Safari", "Google Chrome", "Arc"])
def test_a_list_that_names_a_browser_by_name_never_gives_it(browser) -> None:
    mine = ("Notes", browser)

    assert not app_allowed(mine, browser, "com.example.app")
    assert not app_named(mine, browser)
    assert not app_named(mine, browser.upper())
    # The rest of the list still holds.
    assert app_named(mine, "Notes")


@pytest.mark.parametrize(
    ("bundle_id", "name"),
    [
        ("com.apple.Safari", "Safari"),
        ("com.google.Chrome.app.kjgfgldnnfoeklkmfkjfagphfepbbdan", "Gmail"),
        ("company.thebrowser.Browser", "Arc"),
    ],
)
def test_a_list_that_names_a_browser_by_bundle_id_never_gives_it(bundle_id, name) -> None:
    mine = ("Notes", bundle_id)

    assert not app_allowed(mine, name, bundle_id)
    # A name the list does not hold is still no way in.
    assert not app_allowed(mine, "Notes", bundle_id)
    assert not app_named(mine, bundle_id)
    assert app_allowed(mine, "Notes", "com.apple.Notes")


def test_every_name_the_list_knows_is_a_browser() -> None:
    assert all(is_browser(name) for name in NAMES)
