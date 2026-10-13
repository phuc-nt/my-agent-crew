"""Whether the browser the settings name is on this machine, told without starting one.

Playwright pins the Chromium it drives: the package says which build it wants and looks for
that build alone, so a newer Chromium next to it does not count."""

from __future__ import annotations

import importlib.util
import json
import plistlib
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

MAC_CHROME = Path("/Applications/Google Chrome.app")
PATH_CHROME = ("google-chrome", "google-chrome-stable")
# What is missing, for the one log line and the Connections row.
NO_PACKAGE, NO_BROWSER = "playwright", "browser"


@dataclass(frozen=True)
class Installed:
    ok: bool
    version: str = ""
    missing: str = ""


def package_root() -> Path | None:
    """Where the playwright package is, or None when it is not installed."""
    try:
        spec = importlib.util.find_spec("playwright")
    except (ImportError, ValueError):
        return None
    return Path(spec.origin).parent if spec and spec.origin else None


def browsers_dir(root: Path, env: Mapping[str, str], platform: str = sys.platform) -> Path:
    """Where Playwright keeps the browsers it downloads, as Playwright itself decides it."""
    named = env.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if named == "0":
        return root / "driver" / "package" / ".local-browsers"
    if named:
        return Path(named)
    if platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    if platform == "win32":
        return Path(env.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "ms-playwright"
    return Path(env.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "ms-playwright"


def pinned(root: Path) -> tuple[str, str]:
    """The revision and version of the Chromium this playwright drives, ("", "") if unread."""
    try:
        listed = json.loads((root / "driver" / "package" / "browsers.json").read_text())
        for browser in listed["browsers"]:
            if browser["name"] == "chromium":
                return str(browser["revision"]), str(browser.get("browserVersion", ""))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return "", ""


def chrome_version(app: Path = MAC_CHROME) -> str | None:
    """The version of the Chrome installed here, "" when it is there and does not say, None
    when there is none."""
    if app.is_dir():
        try:
            with (app / "Contents" / "Info.plist").open("rb") as handle:
                return str(plistlib.load(handle).get("CFBundleShortVersionString", ""))
        except (OSError, ValueError):
            return ""
    return "" if any(shutil.which(name) for name in PATH_CHROME) else None


def installed(channel: str, env: Mapping[str, str], root: Path | None = None) -> Installed:
    root = root or package_root()
    if root is None:
        return Installed(False, missing=NO_PACKAGE)
    if channel == "chrome":
        version = chrome_version()
        return Installed(False, missing=NO_BROWSER) if version is None else Installed(True, version)
    revision, version = pinned(root)
    done = browsers_dir(root, env) / f"chromium-{revision}" / "INSTALLATION_COMPLETE"
    if not revision or not done.is_file():
        return Installed(False, version, NO_BROWSER)
    return Installed(True, version)
