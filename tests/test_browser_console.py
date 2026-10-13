"""Whether a person can be shown a window on this machine: what the screen session's two
answers come to, what stands in for them where there is no macOS, and that a system which
will not say is one where no window is tried."""

from __future__ import annotations

import sys

import pytest

from my_agent_crew.browser import console
from my_agent_crew.browser.console import LOCKED, NONE, OPEN, read_console, told


def test_the_three_words_are_what_the_web_is_told_by():
    assert (OPEN, LOCKED, NONE) == ("open", "locked", "none")


@pytest.mark.parametrize(
    ("session", "state"),
    [
        (None, NONE),  # no screen session: started over SSH, or as a daemon
        ((False, False), NONE),  # another person's session is at the screen
        ((False, True), NONE),
        ((True, True), LOCKED),
        ((True, False), OPEN),
    ],
)
def test_a_window_is_shown_only_in_the_session_at_the_screen_while_it_is_unlocked(
    monkeypatch, session, state
):
    assert told(session) == state
    monkeypatch.setattr(console, "_session", lambda: session)
    assert read_console("darwin", {}) == state
    # A display named in the environment says nothing on a Mac.
    assert read_console("darwin", {"DISPLAY": ":0"}) == state


@pytest.mark.parametrize("error", [OSError("no such library"), AttributeError("x"), ValueError()])
def test_a_system_that_will_not_say_is_one_where_no_window_is_tried(monkeypatch, error):
    def refuses():
        raise error

    monkeypatch.setattr(console, "_session", refuses)

    assert read_console("darwin", {}) == NONE


@pytest.mark.parametrize(
    ("env", "state"),
    [
        ({}, NONE),
        ({"DISPLAY": ""}, NONE),
        ({"DISPLAY": ":0"}, OPEN),
        ({"WAYLAND_DISPLAY": "wayland-0"}, OPEN),
        ({"DISPLAY": "", "WAYLAND_DISPLAY": "wayland-0"}, OPEN),
    ],
)
def test_elsewhere_a_display_named_in_the_environment_is_a_screen(monkeypatch, env, state):
    def never():
        raise AssertionError("the Mac's session is not asked for on another system")

    monkeypatch.setattr(console, "_session", never)

    for platform in ("linux", "win32"):
        assert read_console(platform, env) == state


@pytest.mark.skipif(sys.platform != "darwin", reason="reads the Mac's own screen session")
def test_this_macs_own_session_is_read_without_asking_for_anything():
    session = console._session()

    assert session is None or (len(session) == 2 and all(type(x) is bool for x in session))
    assert read_console() == told(session)
