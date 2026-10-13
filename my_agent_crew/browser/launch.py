"""How a Chromium of the crew is started (`pool.py` calls it).

It runs on the agent's profile and behind a proxy that refuses private addresses
(`proxy.py`). The switches and the preferences below are what keeps anything from leaving it
beside that proxy, and keep the browser from running errands of its own."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

VIEWPORT = {"width": 1280, "height": 800}
ACTION_MS, NAVIGATION_MS = 8_000, 20_000
# What the driver turns off in every Chromium it starts. Chromium keeps the last
# `--disable-features` it is given and drops the others, so the crew's switch repeats the
# driver's names, and the driver's own switch is taken out of the command line.
DRIVER_OFF = (
    "AvoidUnnecessaryBeforeUnloadCheckSync",
    "DestroyProfileOnBrowserClose",
    "DialMediaRouteProvider",
    "GlobalMediaControls",
    "HttpsUpgrades",
    "LensOverlay",
    "MediaRouter",
    "PaintHolding",
    "ThirdPartyStoragePartitioning",
    "BlockOriginHeaderModificationOnRedirect",
    "Translate",
    "AutoDeElevate",
    "OptimizationHints",
    "msForceBrowserSignIn",
    "msEdgeUpdateLaunchServicesPreferredVersion",
)
# The crew's own: no connection to a search engine at each page, and no form of a page
# described to the autofill service.
OWN_OFF = ("PreconnectToSearch", "AutofillServerCommunication")
DRIVER_SWITCH = "--disable-features=" + ",".join(DRIVER_OFF)
# Nothing leaves the browser beside the proxy: no direct connection for loopback, no QUIC.
# And the browser runs no errand of its own: its sign-in service and the check-in its push
# service starts with are sent to names that resolve nowhere.
ARGS = (
    "--proxy-bypass-list=<-loopback>",
    "--disable-quic",
    "--disable-features=" + ",".join(DRIVER_OFF + OWN_OFF),
    "--gaia-url=http://gaia.invalid",
    "--gcm-checkin-url=http://gcm.invalid/checkin",
)
# WebRTC sends no UDP, which a proxy cannot carry. The switch of the same name reaches no
# renderer of this Chromium; the preference in the profile is what its pages obey.
PREFERENCES = {"webrtc": {"ip_handling_policy": "disable_non_proxied_udp"}}


def _broken(playwright: Any) -> asyncio.Future[Any] | None:
    """What the driver's connection fails when its process goes away. Playwright promises no
    such thing by name: a release that moves it leaves a lost driver unnoticed, which the test
    that ends a driver's process would say."""
    connection = getattr(getattr(playwright, "_impl_obj", None), "_connection", None)
    return getattr(getattr(connection, "_transport", None), "on_error_future", None)


class Driver:
    """The one Playwright driver every browser of the crew is started through. It is started
    at the first launch and not before: a crew where no agent browses never loads it. One that
    did not start, or went away later, is not kept: the next launch starts another."""

    def __init__(self, lost: Callable[[], None] = lambda: None) -> None:
        self._started: asyncio.Future[Any] | None = None
        # Told when a driver that was up went away, and every browser it started with it.
        self._lost = lost

    async def get(self) -> Any:
        if self._started is None:
            from playwright.async_api import async_playwright  # absent where no agent browses

            started = self._started = asyncio.ensure_future(async_playwright().start())
            started.add_done_callback(self._settled)
        return await asyncio.shield(self._started)

    def _settled(self, started: asyncio.Future[Any]) -> None:
        if started.cancelled() or started.exception():
            self._drop(started)
        elif (broken := _broken(started.result())) is not None:
            broken.add_done_callback(lambda gone: self._drop(started, gone))

    def _drop(self, started: asyncio.Future[Any], gone: asyncio.Future[Any] | None = None) -> None:
        if gone is not None and not gone.cancelled():
            gone.exception()  # read here, or the loop logs it as an error nobody took
        if self._started is started:
            self._started = None
            if gone is not None:
                self._lost()

    async def stop(self) -> None:
        started, self._started = self._started, None
        if started is not None:
            with contextlib.suppress(Exception):
                await (await started).stop()


def _over(kept: Any, insisted: dict[str, Any]) -> dict[str, Any]:
    merged = dict(kept) if isinstance(kept, dict) else {}
    for key, value in insisted.items():
        merged[key] = _over(merged.get(key), value) if isinstance(value, dict) else value
    return merged


def prepare(profile: Path) -> None:
    """The profile's folder, private, with the preferences the crew insists on written over
    whatever the browser kept there at its last run."""
    profile.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = profile / "Default" / "Preferences"
    try:
        kept = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        kept = None
    merged = _over(kept, PREFERENCES)
    if merged != kept:
        path.parent.mkdir(mode=0o700, exist_ok=True)
        fresh = path.with_name("Preferences.crew")
        fresh.write_text(json.dumps(merged), encoding="utf-8")
        os.replace(fresh, path)


async def launch(driver: Any, profile: Path, channel: str, proxy: dict[str, str]) -> Any:
    """A Chromium on `profile` whose every request goes to `proxy`.

    On macOS it keeps Chromium's own sandbox, which the driver would switch off: a page that
    breaks out of its renderer is still not the server's user. Elsewhere that sandbox needs a
    set-up the crew cannot count on, so it stays as the driver leaves it."""
    await asyncio.to_thread(prepare, profile)
    context = await driver.chromium.launch_persistent_context(
        str(profile),
        headless=True,
        channel=channel,
        proxy=proxy,
        accept_downloads=False,
        viewport=VIEWPORT,
        args=list(ARGS),
        ignore_default_args=[DRIVER_SWITCH],
        chromium_sandbox=sys.platform == "darwin",
    )
    context.set_default_timeout(ACTION_MS)
    context.set_default_navigation_timeout(NAVIGATION_MS)
    return context
