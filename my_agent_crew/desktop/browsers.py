"""The web browsers the desktop never acts in, by bundle id and by name.

A page belongs to the browser tools, which keep the crew's own web page and the private
network out of reach and fence what a page says as data. Clicks and keys the desktop sent
into a browser window would go round all of that, so no agent's list may name a browser,
and a browser is never taken for an application a list names (`policy.is_browser`). The
helper refuses to act in one too, from the same bundle ids: `Browsers.swift` holds them,
and a test holds this list to that one.
"""

from __future__ import annotations

# An id listed here, or one that goes on from it after a dot.
BUNDLE_IDS = (
    "com.apple.Safari",
    "com.apple.SafariTechnologyPreview",
    "com.google.Chrome",
    "com.google.chrome.for.testing",
    "org.chromium.Chromium",
    "org.mozilla.firefox",
    "org.mozilla.firefoxdeveloperedition",
    "org.mozilla.nightly",
    "org.torproject.torbrowser",
    "com.microsoft.edgemac",
    "com.brave.Browser",
    "company.thebrowser.Browser",
    "company.thebrowser.dia",
    "com.operasoftware",
    "com.vivaldi.Vivaldi",
    "com.kagi.kagimacOS",
    "com.duckduckgo.macos.browser",
    "app.zen-browser.zen",
    "ru.yandex.desktop.yandex-browser",
)

# What a person writes in an agent's list for one, the names the system shows included.
NAMES = (
    "Safari",
    "Safari Technology Preview",
    "Google Chrome",
    "Chrome",
    "Google Chrome for Testing",
    "Chromium",
    "Firefox",
    "Firefox Developer Edition",
    "Firefox Nightly",
    "Tor Browser",
    "Microsoft Edge",
    "Edge",
    "Brave Browser",
    "Brave",
    "Arc",
    "Dia",
    "Opera",
    "Opera GX",
    "Vivaldi",
    "Orion",
    "DuckDuckGo",
    "Zen",
    "Zen Browser",
    "Yandex",
    "LibreWolf",
    "Waterfox",
)
