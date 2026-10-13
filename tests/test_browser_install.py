"""Telling whether the browser the settings name is on this machine, without starting one."""

from __future__ import annotations

import json
from pathlib import Path

from my_agent_crew.browser import install
from my_agent_crew.browser.install import NO_BROWSER, NO_PACKAGE, Installed, browsers_dir, installed


def package(tmp_path: Path, browsers: list[dict]) -> Path:
    root = tmp_path / "playwright"
    (root / "driver" / "package").mkdir(parents=True)
    (root / "driver" / "package" / "browsers.json").write_text(json.dumps({"browsers": browsers}))
    return root


CHROMIUM = [
    {"name": "chromium-headless-shell", "revision": "9", "browserVersion": "1.0"},
    {"name": "chromium", "revision": "1243", "browserVersion": "153.0.8010.12"},
]


def downloaded(cache: Path, revision: str, complete: bool = True) -> dict[str, str]:
    (cache / f"chromium-{revision}").mkdir(parents=True)
    if complete:
        (cache / f"chromium-{revision}" / "INSTALLATION_COMPLETE").write_text("")
    return {"PLAYWRIGHT_BROWSERS_PATH": str(cache)}


def test_the_pinned_chromium_downloaded_whole_is_installed_and_says_its_version(tmp_path):
    env = downloaded(tmp_path / "cache", "1243")

    assert installed("chromium", env, package(tmp_path, CHROMIUM)) == Installed(
        True, "153.0.8010.12"
    )


def test_another_build_of_chromium_is_not_the_one_this_playwright_drives(tmp_path):
    env = downloaded(tmp_path / "cache", "1242")

    assert installed("chromium", env, package(tmp_path, CHROMIUM)) == Installed(
        False, "153.0.8010.12", NO_BROWSER
    )


def test_a_download_that_never_finished_is_not_installed(tmp_path):
    env = downloaded(tmp_path / "cache", "1243", complete=False)

    assert not installed("chromium", env, package(tmp_path, CHROMIUM)).ok


def test_a_package_that_names_no_chromium_has_none(tmp_path):
    env = downloaded(tmp_path / "cache", "")
    (tmp_path / "cache" / "chromium-" / "INSTALLATION_COMPLETE").touch()

    assert installed("chromium", env, package(tmp_path, [])) == Installed(False, "", NO_BROWSER)
    (tmp_path / "playwright" / "driver" / "package" / "browsers.json").write_text("not json")
    assert installed("chromium", env, tmp_path / "playwright") == Installed(False, "", NO_BROWSER)


def test_without_the_package_nothing_is_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(install, "package_root", lambda: None)

    assert installed("chromium", {}) == Installed(False, "", NO_PACKAGE)
    assert installed("chrome", {}) == Installed(False, "", NO_PACKAGE)


def test_chrome_is_installed_when_the_machine_has_it(tmp_path, monkeypatch):
    root = package(tmp_path, CHROMIUM)
    monkeypatch.setattr(install, "chrome_version", lambda: "155.0.1")
    assert installed("chrome", {}, root) == Installed(True, "155.0.1")
    monkeypatch.setattr(install, "chrome_version", lambda: "")
    assert installed("chrome", {}, root) == Installed(True, "")
    monkeypatch.setattr(install, "chrome_version", lambda: None)
    assert installed("chrome", {}, root) == Installed(False, "", NO_BROWSER)


def test_the_version_of_chrome_is_read_from_the_application_without_starting_it(
    tmp_path, monkeypatch
):
    import plistlib

    app = tmp_path / "Google Chrome.app"
    (app / "Contents").mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_bytes(
        plistlib.dumps({"CFBundleShortVersionString": "155.0.7000.1"})
    )
    monkeypatch.setattr(install.shutil, "which", lambda name: None)

    assert install.chrome_version(app) == "155.0.7000.1"
    (app / "Contents" / "Info.plist").write_bytes(b"not a plist")
    assert install.chrome_version(app) == ""
    assert install.chrome_version(tmp_path / "none.app") is None
    monkeypatch.setattr(
        install.shutil, "which", lambda name: "/usr/bin/x" if name == "google-chrome" else None
    )
    assert install.chrome_version(tmp_path / "none.app") == ""


def test_browsers_are_looked_for_where_playwright_keeps_them(tmp_path):
    root, home = tmp_path / "playwright", Path.home()

    assert browsers_dir(root, {"PLAYWRIGHT_BROWSERS_PATH": "/opt/b"}) == Path("/opt/b")
    assert browsers_dir(root, {"PLAYWRIGHT_BROWSERS_PATH": "0"}) == (
        root / "driver" / "package" / ".local-browsers"
    )
    assert browsers_dir(root, {}, "darwin") == home / "Library" / "Caches" / "ms-playwright"
    assert browsers_dir(root, {}, "linux") == home / ".cache" / "ms-playwright"
    assert browsers_dir(root, {"XDG_CACHE_HOME": "/x"}, "linux") == Path("/x/ms-playwright")
    assert browsers_dir(root, {"LOCALAPPDATA": "/l"}, "win32") == Path("/l/ms-playwright")
    assert browsers_dir(root, {}, "win32") == home / "AppData" / "Local" / "ms-playwright"


def test_the_package_in_this_environment_is_found_with_its_chromium_pinned():
    root = install.package_root()

    assert root is not None and (root / "driver" / "package" / "browsers.json").is_file()
    revision, version = install.pinned(root)
    assert revision.isdigit() and version.count(".") == 3
