"""Whether a person can be shown a window on this machine now: it has a screen session, that
session is the one at the screen, and the screen is not locked.

Read from the system each time it is asked, through `ctypes` on macOS and nothing else: it
asks for no permission and shows nothing. Elsewhere a display named in the environment is
taken to be a screen someone is at."""

from __future__ import annotations

import ctypes
import os
import sys
from collections.abc import Mapping

# A window can be opened; the screen is locked; there is no screen session to open one in.
OPEN, LOCKED, NONE = "open", "locked", "none"
FRAMEWORKS = "/System/Library/Frameworks/{name}.framework/{name}"
ON_CONSOLE, SCREEN_LOCKED = b"kCGSSessionOnConsoleKey", b"CGSSessionScreenIsLocked"
UTF8 = 0x08000100
DISPLAYS = ("DISPLAY", "WAYLAND_DISPLAY")


def read_console(platform: str = sys.platform, env: Mapping[str, str] = os.environ) -> str:
    if platform != "darwin":
        return OPEN if any(env.get(name) for name in DISPLAYS) else NONE
    try:
        return told(_session())
    except (OSError, AttributeError, ValueError):
        return NONE  # a system that will not say is one where no window is tried


def told(session: tuple[bool, bool] | None) -> str:
    """What a screen session's two answers come to: whether it is the one at the screen, and
    whether that screen is locked. None is a process with no screen session at all."""
    if session is None or not session[0]:
        return NONE  # another person's session is the one at the screen
    return LOCKED if session[1] else OPEN


def _session() -> tuple[bool, bool] | None:
    """The two answers of this process's screen session; None where it has none: started
    over SSH, or as a daemon."""
    cf = ctypes.CDLL(FRAMEWORKS.format(name="CoreFoundation"))
    cg = ctypes.CDLL(FRAMEWORKS.format(name="CoreGraphics"))
    pointer = ctypes.c_void_p
    cg.CGSessionCopyCurrentDictionary.restype = pointer
    cf.CFStringCreateWithCString.restype = pointer
    cf.CFStringCreateWithCString.argtypes = [pointer, ctypes.c_char_p, ctypes.c_uint32]
    cf.CFDictionaryGetValue.restype = pointer
    cf.CFDictionaryGetValue.argtypes = [pointer, pointer]
    cf.CFRelease.argtypes = [pointer]
    yes = pointer.in_dll(cf, "kCFBooleanTrue").value

    def said(session: int, key: bytes) -> bool:
        name = cf.CFStringCreateWithCString(None, key, UTF8)
        try:
            return cf.CFDictionaryGetValue(session, name) == yes
        finally:
            cf.CFRelease(name)

    session = cg.CGSessionCopyCurrentDictionary()
    if not session:
        return None
    try:
        return said(session, ON_CONSOLE), said(session, SCREEN_LOCKED)
    finally:
        cf.CFRelease(session)
