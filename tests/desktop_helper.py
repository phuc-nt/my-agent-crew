"""A stand-in for the desktop helper: a Unix-socket server that answers the helper's commands
from a state the test sets, and keeps every request it was sent.

It is the only helper a test ever talks to. Its socket lives in a short folder of its own
under /tmp, because a pytest folder is longer than the 103 bytes a socket path may have; the
folder is removed when the helper stops.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import shutil
import struct
import tempfile
import zlib
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from my_agent_crew.desktop.browsers import BUNDLE_IDS

VERSION, PROTOCOL = "0.1.0", 1
# What each command needs before it does anything, in the order the helper checks.
NEEDS = {
    "apps": (),
    "windows": ("screen",),
    "screenshot": ("screen",),
    "ax": ("accessibility",),
    "act": ("accessibility",),
}
EFFECTS = {"set_value": "set", "focus_app": "focused"}
# The actions the helper sends to a point, whose topmost element it looks at first.
POINTED = ("click", "double_click", "right_click", "drag", "scroll")


# The screen of the stand-in, small so its pictures are.
WIDTH, HEIGHT = 16, 10
# Where a point of an action has to lie: inside the frame it was read off.
POINTS = {"x": WIDTH, "y": HEIGHT, "to_x": WIDTH, "to_y": HEIGHT}
# The helper's own words for a frame that is not the last one it pictured, and for a point
# that is not on that picture.
STALE = "That is not the last frame captured of display 1; take a new screenshot."
OFF_THE_PICTURE = f"The point is outside the picture, which is {WIDTH} by {HEIGHT} pixels."
CONTROL_TEXT = "`text` holds a control character other than tab and the line breaks."


def png(shade: int = 0, width: int = WIDTH, height: int = HEIGHT) -> bytes:
    """A real picture of one colour, a different one for each shade."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        )

    head = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    rows = zlib.compress((b"\0" + bytes((shade % 256, 0, 0)) * width) * height)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"IDAT", rows) + chunk(b"IEND", b"")


def frame(number: int) -> str:
    return f"{number:016x}-{WIDTH}x{HEIGHT}-1"


def outline_name(number: int) -> str:
    """What the stand-in names its outlines: the real helper draws a name at random, this
    one counts, so a test knows the tag each of its outlines shows."""
    return f"{number:04x}" + "0" * 12


def ref(node: str, number: int = 1) -> str:
    """A ref as the stand-in's outline `number` shows it: with the tag of that outline."""
    return f"{node}-{number:04x}"


@dataclass
class App:
    app: str
    bundle_id: str
    pid: int
    hidden: bool = False
    window: str | None = None
    nodes: list[dict] = field(default_factory=list)
    truncated: bool = False

    def named(self, text: str) -> bool:
        return text.lower() in (self.app.lower(), self.bundle_id.lower())

    @property
    def browser(self) -> bool:
        """As the helper tells a browser: by its bundle id, whatever the case, or one that
        goes on from a browser's after a dot."""
        mine = self.bundle_id.lower()
        return any(mine == b.lower() or mine.startswith(f"{b.lower()}.") for b in BUNDLE_IDS)


def holds_control(text: Any) -> bool:
    """Whether a text holds a control character the helper refuses: any but tab, LF and CR."""
    return isinstance(text, str) and any(
        (ord(char) < 0x20 and char not in "\t\n\r") or 0x7F <= ord(char) <= 0x9F for char in text
    )


class Refused(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code, self.detail = code, detail


@dataclass
class FakeHelper:
    folder: Path
    apps: list[App] = field(default_factory=list)
    front: str | None = None  # the name of the application in front
    locked: bool = False
    display_asleep: bool = False
    screen_recording: bool = True
    accessibility: bool = True
    secure_input: bool = False
    # Something else lies on top where an action points: another window, a dialog.
    covered: bool = False
    shot: int = 1  # which picture the screen shows now
    # The last frame handed out. An action is read against that picture and no other: the
    # helper knows of no screen but the one it last pictured. A stand-in starts as one whose
    # first screen was looked at already.
    latest: str | None = frame(1)
    # How many outlines were given, the name of the last and the application it was read
    # of: a ref means an element only as one of that outline.
    outlines: int = 0
    outline: str | None = None
    outline_of: str | None = None
    # A code a command is refused with whatever the state says, as (code, detail).
    fail: dict[str, tuple[str, str]] = field(default_factory=dict)
    # Whole answers given instead of the real one, first in first out, per command.
    scripted: dict[str, list[dict]] = field(default_factory=dict)
    # Bytes sent as they are instead of an answer; None answers properly. Bytes that do not
    # end a line are the last thing the connection carries.
    raw: bytes | None = None
    silent: bool = False  # reads the request and never answers
    hangs_up: bool = False  # closes the connection without a word
    other_id: bool = False  # answers under an id of its own
    # What `act` does to the desktop once it has answered.
    after_act: Any = None
    requests: list[dict] = field(default_factory=list)
    _server: asyncio.AbstractServer | None = None
    _open: set[asyncio.StreamWriter] = field(default_factory=set)
    _stopping: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def path(self) -> Path:
        return self.folder / "sock"

    def sent(self, cmd: str) -> list[dict]:
        """The requests of one command, in the order they came."""
        return [request for request in self.requests if request.get("cmd") == cmd]

    def running(self, name: str) -> App | None:
        return next((app for app in self.apps if app.named(name)), None)

    @property
    def frame_id(self) -> str:
        return frame(self.shot)

    async def start(self) -> None:
        self._server = await asyncio.start_unix_server(self._serve, path=str(self.path))

    async def stop(self) -> None:
        self._stopping.set()
        for writer in list(self._open):
            writer.close()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
        shutil.rmtree(self.folder, ignore_errors=True)

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._open.add(writer)
        try:
            while line := await reader.readline():
                request = json.loads(line)
                self.requests.append(request)
                if self.hangs_up:
                    return
                if self.silent:
                    await self._stopping.wait()
                    return
                writer.write(self.raw if self.raw is not None else self._line(request))
                await writer.drain()
                if self.raw is not None and not self.raw.endswith(b"\n"):
                    return  # it died in the middle of its answer
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            self._open.discard(writer)
            writer.close()

    def _line(self, request: dict) -> bytes:
        cmd = request.get("cmd")
        request_id = "another" if self.other_id else request.get("id", "")
        try:
            if self.scripted.get(cmd):
                body = self.scripted[cmd].pop(0)
            else:
                body = self._answer(cmd, request)
            answer = {"id": request_id, "ok": True, **body}
        except Refused as refused:
            answer = {"id": request_id, "ok": False, "error": refused.code}
            answer["detail"] = refused.detail
        return json.dumps(answer, ensure_ascii=False).encode() + b"\n"

    def _answer(self, cmd: Any, request: dict) -> dict:
        if cmd in self.fail:
            raise Refused(*self.fail[cmd])
        if cmd == "state":
            return self._state()
        if cmd == "request_permissions":
            if self.locked:
                raise Refused("locked", "the console is locked")
            return {"screen_recording": self.screen_recording, "accessibility": self.accessibility}
        if cmd not in NEEDS:
            raise Refused("unknown_command", f"no command {cmd}")
        if self.locked:
            raise Refused("locked", "the console is locked")
        if self.display_asleep:
            raise Refused("display_asleep", "the display is asleep")
        if "screen" in NEEDS[cmd] and not self.screen_recording:
            raise Refused("permission_missing:screen", "Screen Recording is not granted")
        if "accessibility" in NEEDS[cmd] and not self.accessibility:
            raise Refused("permission_missing:accessibility", "Accessibility is not granted")
        return getattr(self, f"_{cmd}")(request)

    def _frontmost(self) -> dict | None:
        app = self.running(self.front) if self.front else None
        return {"app": app.app, "bundle_id": app.bundle_id, "pid": app.pid} if app else None

    def _state(self) -> dict:
        return {
            "version": VERSION,
            "protocol": PROTOCOL,
            "locked": self.locked,
            "display_asleep": self.display_asleep,
            "screen_recording": self.screen_recording,
            "accessibility": self.accessibility,
            "secure_input": self.secure_input,
            "displays": [{"id": 1, "width": WIDTH, "height": HEIGHT, "scale": 1, "main": True}],
            "frontmost": self._frontmost(),
        }

    def _apps(self, _request: dict) -> dict:
        rows = [
            {
                "app": app.app,
                "bundle_id": app.bundle_id,
                "pid": app.pid,
                "frontmost": app.app == self.front,
                "hidden": app.hidden,
            }
            for app in self.apps
        ]
        return {"apps": rows}

    def _windows(self, _request: dict) -> dict:
        return {"windows": []}

    def _screenshot(self, request: dict) -> dict:
        # Remembered also when nothing changed: the caller's frame is the latest one again.
        self.latest = self.frame_id
        answer = {
            "frame_id": self.frame_id,
            "display": 1,
            "width": WIDTH,
            "height": HEIGHT,
            "scale": 1,
            "unchanged": request.get("since") == self.frame_id,
        }
        if not answer["unchanged"]:
            answer["png_base64"] = base64.b64encode(png(self.shot)).decode()
        return answer

    def _ax(self, request: dict) -> dict:
        app = self.running(request.get("app") or self.front or "")
        if app is None:
            raise Refused("app_not_running", f"{request.get('app')} is not running")
        self.outlines += 1
        self.outline, self.outline_of = outline_name(self.outlines), app.app
        return {
            "app": app.app,
            "pid": app.pid,
            "window": app.window,
            "truncated": app.truncated,
            "nodes": app.nodes,
            "outline": self.outline,
        }

    def _names(self, app: App, request: dict) -> bool:
        """Whether the ref of a request means an element: only as one of the outline that
        was given last, and only when that outline was read of this application."""
        if request.get("outline") != self.outline or self.outline_of != app.app:
            return False
        return any(node["ref"] == request["ref"] for node in app.nodes)

    def _act(self, request: dict) -> dict:
        kind, app = request.get("kind"), self.running(request.get("app", ""))
        if kind != "focus_app" and "ref" in request:
            if not isinstance(request.get("outline"), str):
                raise Refused("bad_request", "`outline` is required with a `ref`.")
        if holds_control(request.get("text")):
            raise Refused("bad_request", CONTROL_TEXT)
        # A browser is refused whatever the list says: the one asked for, or the one in front.
        target = app if kind == "focus_app" else self.running(self.front or "")
        if target is not None and target.browser:
            raise Refused("browser_app", "That application is a web browser.")
        if kind == "focus_app":
            if app is None:
                raise Refused("app_not_running", f"{request.get('app')} is not running")
            self.front = app.app
        elif app is None or app.app != self.front:
            # As the helper words it: the application that is in front is not named.
            raise Refused(
                "app_mismatch", "The frontmost application is not the one named in `app`."
            )
        elif "frame_id" in request and request["frame_id"] != self.latest:
            raise Refused("frame_mismatch", STALE)
        elif "ref" in request and not self._names(app, request):
            raise Refused("ref_unknown", f"no element {request['ref']} in the last outline")
        elif any(not 0 <= request.get(key, 0) < most for key, most in POINTS.items()):
            raise Refused("bad_request", OFF_THE_PICTURE)
        elif self.covered and kind in POINTED:
            raise Refused("point_covered", "Another window lies on top at that point.")
        if self.after_act is not None:
            self.after_act(self)
        return {"effect": EFFECTS.get(kind, "posted"), "frontmost": self._frontmost()}


def socket_folder() -> Path:
    return Path(tempfile.mkdtemp(prefix="dh", dir="/tmp"))


@contextlib.asynccontextmanager
async def listening(**state: Any) -> AsyncIterator[FakeHelper]:
    """A helper that answers for the length of the block, and its folder gone afterwards."""
    helper = FakeHelper(socket_folder(), **state)
    try:
        await helper.start()
        yield helper
    finally:
        await helper.stop()


def desk() -> list[App]:
    """A desktop a test can start from: three applications, the first of them in front."""
    notes = App(
        "Notes",
        "com.apple.Notes",
        501,
        window="Việc hôm nay",
        nodes=[
            {"ref": "a1", "depth": 0, "role": "AXWindow", "title": "Việc hôm nay"},
            {"ref": "a2", "depth": 1, "role": "AXButton", "title": "Ghi mới", "enabled": True},
            {
                "ref": "a3",
                "depth": 1,
                "role": "AXTextArea",
                "value": "mua sữa",
                "focused": True,
            },
            {
                "ref": "a4",
                "depth": 1,
                "role": "AXSecureTextField",
                "title": "Mật khẩu",
                "secure": True,
            },
            {"ref": "a5", "depth": 2, "role": "AXButton", "title": "Xoá", "enabled": False},
        ],
    )
    bank = App("Ngân hàng", "vn.bank.app", 777, window="Số dư")
    bank.nodes = [{"ref": "a1", "depth": 0, "role": "AXStaticText", "value": "12.345.678 đ"}]
    return [notes, App("TextEdit", "com.apple.TextEdit", 502, window="Không tên"), bank]
