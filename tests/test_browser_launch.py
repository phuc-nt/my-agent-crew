"""How a Chromium of the crew is started: nothing leaves it beside its proxy, what the driver
turns off stays off, and a driver that did not start or went away is replaced. The one nobody
sees and the window a person signs in through get the same profile, the same proxy and the
same switches, and differ only in being shown."""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import socket
import stat
import struct
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import playwright
import pytest

from my_agent_crew.browser import launch as launch_module
from my_agent_crew.browser.launch import (
    ACTION_MS,
    ARGS,
    DRIVER_OFF,
    DRIVER_SWITCH,
    NAVIGATION_MS,
    OWN_OFF,
    PREFERENCES,
    VIEWPORT,
    Driver,
    Stuck,
    launch,
    prepare,
    shut_down,
)
from tests.browser_servers import browsers, drivers, sites

COOKIE = 0x2112A442
POLICY = "disable_non_proxied_udp"
PROXY = {"server": "http://127.0.0.1:9"}


class Stun:
    """A UDP port on loopback that keeps every datagram it is sent and answers a binding
    request the way a STUN server would: what a page asks to learn the machine's address."""

    def __init__(self) -> None:
        self.hits: list[int] = []
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.settimeout(0.2)
        self.port = self._socket.getsockname()[1]
        self._alive = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while self._alive:
            try:
                data, peer = self._socket.recvfrom(2000)
            except OSError:
                continue
            self.hits.append(len(data))
            if len(data) >= 20 and data[:2] == b"\x00\x01":
                port = peer[1] ^ (COOKIE >> 16)
                address = struct.unpack("!I", socket.inet_aton(peer[0]))[0] ^ COOKIE
                mapped = struct.pack("!HHBBHI", 0x0020, 8, 0, 1, port, address)
                head = struct.pack("!HHI", 0x0101, len(mapped), COOKIE) + data[8:20]
                self._socket.sendto(head + mapped, peer)

    def close(self) -> None:
        self._alive = False
        self._thread.join(2)
        self._socket.close()


def rtc(port: int) -> str:
    """A page that asks a STUN server for the machine's address and puts the kinds of the
    candidates it was given in its title when the browser is done looking."""
    return f"""<title>looking</title><script>
const kinds = [];
const peer = new RTCPeerConnection({{iceServers: [{{urls: 'stun:127.0.0.1:{port}'}}]}});
peer.onicecandidate = found => {{
  if (found.candidate) kinds.push(found.candidate.candidate.split(' ')[7]);
  else document.title = 'done ' + kinds.join(' ');
}};
peer.createDataChannel('x');
peer.createOffer().then(offer => peer.setLocalDescription(offer));
</script>"""


async def candidates(pool, address: str) -> list[str]:
    tab = await (await pool.session("coach")).tabs.open("c1")
    await tab.page.goto(address)
    await tab.page.wait_for_function("document.title.startsWith('done')", timeout=20_000)
    await asyncio.sleep(0.5)  # a datagram on its way is in the listener's list by now
    return (await tab.page.title()).split()[1:]


async def test_a_page_sends_no_datagram_around_the_proxy_also_on_a_profile_used_before(tmp_path):
    """A proxy carries no UDP, so whatever WebRTC sent would go straight to an address the
    page chose, a private one included."""
    stun = Stun()
    try:
        with sites({"/rtc": rtc(stun.port)}) as (site,):
            async with browsers(tmp_path / "browser", site) as pool:
                first = await candidates(pool, site.url("/rtc"))
                assert await pool.stop("coach") is True
                again = await candidates(pool, site.url("/rtc"))

        assert (first, again, stun.hits) == ([], [], [])
    finally:
        stun.close()


async def test_a_plain_http_address_is_asked_for_on_its_own_port_and_no_other(tmp_path):
    """Chromium tries the https port first for an address written with http unless that is
    turned off. The driver turns it off, and the crew's own switch must not undo the driver's:
    Chromium obeys the last list of features it is given and drops the others."""
    asked: list[int] = []

    def allow(_address: str, port: int) -> bool:
        asked.append(port)
        return False

    async with browsers(
        tmp_path / "browser", allow=allow, resolver=lambda _: ["127.0.0.1"]
    ) as pool:
        tab = await (await pool.session("coach")).tabs.open("c1")
        answer = await tab.page.goto("http://shop.example.com/")

    assert answer.status == 403 and set(asked) == {80}


def command_line(profile: Path) -> str:
    """The browser process on `profile` as the system lists it, without its helpers."""
    listing = subprocess.run(
        ["ps", "-axww", "-o", "args="], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    (main,) = [x for x in listing if f"--user-data-dir={profile}" in x and "--type=" not in x]
    return main


async def test_a_browser_is_given_one_list_of_features_to_turn_off_the_drivers_and_the_crews(
    tmp_path,
):
    async with browsers(tmp_path / "browser") as pool:
        await pool.session("coach")
        main = command_line(tmp_path / "browser" / "coach")

    lists = [word.split()[0] for word in main.split(" --") if word.startswith("disable-features=")]
    assert len(lists) == 1
    assert sorted(lists[0].split("=", 1)[1].split(",")) == sorted(DRIVER_OFF + OWN_OFF)
    # Chromium's own sandbox is kept on macOS, and left as the driver has it elsewhere.
    assert (" --no-sandbox" in main) is (sys.platform != "darwin")


def test_the_names_repeated_from_the_driver_are_the_ones_the_installed_driver_turns_off():
    """The driver's switch is taken out of the command line by its exact text: a driver whose
    list changed would be left with its own switch, and Chromium with two."""
    source = Path(playwright.__file__).parent / "driver" / "package" / "lib" / "coreBundle.js"
    listed = re.search(r"disabledFeatures = \[(.*?)\n\s*\];", source.read_text("utf-8"), re.S)

    assert tuple(re.findall(r'^\s*"(\w+)",?\s*$', listed.group(1), re.M)) == DRIVER_OFF
    assert DRIVER_SWITCH == "--disable-features=" + ",".join(DRIVER_OFF)
    assert not set(OWN_OFF) & set(DRIVER_OFF)


class Context:
    def __init__(self) -> None:
        self.timeouts: dict[str, int] = {}

    def set_default_timeout(self, ms: int) -> None:
        self.timeouts["action"] = ms

    def set_default_navigation_timeout(self, ms: int) -> None:
        self.timeouts["navigation"] = ms


class Chromium:
    def __init__(self) -> None:
        self.asked: dict = {}

    async def launch_persistent_context(self, profile: str, **options) -> Context:
        self.asked = {"profile": profile, **options}
        return Context()


@pytest.mark.parametrize(("platform", "kept"), [("darwin", True), ("linux", False)])
async def test_chromiums_own_sandbox_is_kept_where_it_needs_no_set_up(
    tmp_path, monkeypatch, platform, kept
):
    monkeypatch.setattr(launch_module, "sys", SimpleNamespace(platform=platform))
    chromium, proxy = Chromium(), {"server": "http://127.0.0.1:1"}

    await launch(SimpleNamespace(chromium=chromium), tmp_path / "coach", "chromium", proxy)

    assert chromium.asked["chromium_sandbox"] is kept
    assert chromium.asked["ignore_default_args"] == [DRIVER_SWITCH]
    assert chromium.asked["proxy"] is proxy and chromium.asked["accept_downloads"] is False
    assert chromium.asked["profile"] == str(tmp_path / "coach")
    assert kept_in(tmp_path / "coach") == PREFERENCES


def kept_in(profile: Path) -> object:
    return json.loads((profile / "Default" / "Preferences").read_text(encoding="utf-8"))


async def test_an_agents_own_browser_is_started_unseen_with_a_page_of_one_size(tmp_path):
    chromium, profile = Chromium(), tmp_path / "browser" / "coach"

    context = await launch(SimpleNamespace(chromium=chromium), profile, "chromium", PROXY)

    assert chromium.asked == {
        "profile": str(profile),
        "headless": True,
        "channel": "chromium",
        "proxy": PROXY,
        "accept_downloads": False,
        "args": list(ARGS),
        "ignore_default_args": [DRIVER_SWITCH],
        "chromium_sandbox": sys.platform == "darwin",
        "viewport": VIEWPORT,
    }
    assert context.timeouts == {"action": ACTION_MS, "navigation": NAVIGATION_MS}
    # The folder that will hold what the agent is signed in to is its owner's alone.
    assert profile.is_dir() and profile.stat().st_mode & 0o777 == 0o700


async def test_a_window_is_started_shown_sized_by_the_person_and_behind_the_same_proxy(tmp_path):
    chromium, profile = Chromium(), tmp_path / "browser" / "coach"

    await launch(SimpleNamespace(chromium=chromium), profile, "chrome", PROXY, headed=True)

    assert chromium.asked == {
        "profile": str(profile),
        "headless": False,
        "channel": "chrome",
        "proxy": PROXY,
        "accept_downloads": False,
        # What keeps anything from leaving beside the proxy is the window's too: the switches,
        # the driver's list folded into the crew's, and the preferences in the profile.
        "args": list(ARGS),
        "ignore_default_args": [DRIVER_SWITCH],
        "chromium_sandbox": sys.platform == "darwin",
        "no_viewport": True,
    }
    assert kept_in(profile) == PREFERENCES


async def test_a_file_a_page_sends_is_kept_only_where_a_folder_is_named_for_it(tmp_path):
    chromium, held = Chromium(), tmp_path / "held"
    driver = SimpleNamespace(chromium=chromium)

    await launch(driver, tmp_path / "coach", "chromium", PROXY, downloads=held)

    assert (chromium.asked["accept_downloads"], chromium.asked["downloads_path"]) == (
        True,
        str(held),
    )


def test_a_new_profile_is_private_and_starts_with_the_crews_preferences(tmp_path):
    profile = tmp_path / "browser" / "coach"

    prepare(profile)

    assert stat.S_IMODE(profile.stat().st_mode) == 0o700
    assert kept_in(profile) == PREFERENCES == {"webrtc": {"ip_handling_policy": POLICY}}


def test_what_the_browser_kept_stays_and_the_crews_preferences_are_written_over_it(tmp_path):
    profile = tmp_path / "coach"
    (profile / "Default").mkdir(parents=True)
    kept = {
        "profile": {"name": "Coach", "exit_type": "Normal"},
        "webrtc": {"ip_handling_policy": "default", "multiple_routes_enabled": True},
    }
    (profile / "Default" / "Preferences").write_text(json.dumps(kept), encoding="utf-8")

    prepare(profile)

    assert kept_in(profile) == {
        "profile": {"name": "Coach", "exit_type": "Normal"},
        "webrtc": {"ip_handling_policy": POLICY, "multiple_routes_enabled": True},
    }
    assert [p.name for p in (profile / "Default").iterdir()] == ["Preferences"]


@pytest.mark.parametrize("written", ["{not json", "[1, 2]", '"text"', "", '{"webrtc": "none"}'])
def test_preferences_that_cannot_be_read_as_such_are_replaced(tmp_path, written):
    profile = tmp_path / "coach"
    (profile / "Default").mkdir(parents=True)
    (profile / "Default" / "Preferences").write_text(written, encoding="utf-8")

    prepare(profile)

    assert kept_in(profile) == PREFERENCES


def test_preferences_that_already_say_so_are_not_written_again(tmp_path):
    profile = tmp_path / "coach"
    prepare(profile)
    before = (profile / "Default" / "Preferences").stat().st_ino

    prepare(profile)

    assert (profile / "Default" / "Preferences").stat().st_ino == before


async def test_a_driver_that_did_not_start_is_not_kept_and_the_next_launch_starts_another(
    monkeypatch,
):
    starts, up = [], SimpleNamespace()

    class Manager:
        async def start(self) -> SimpleNamespace:
            starts.append(len(starts))
            await asyncio.sleep(0)
            if len(starts) == 1:
                raise RuntimeError("the driver did not start")
            return up

    monkeypatch.setattr("playwright.async_api.async_playwright", Manager)
    driver = Driver()

    failed = await asyncio.gather(driver.get(), driver.get(), return_exceptions=True)
    assert [type(f) for f in failed] == [RuntimeError, RuntimeError] and starts == [0]

    assert await driver.get() is up and await driver.get() is up
    assert starts == [0, 1]


async def test_a_driver_that_went_away_takes_its_browsers_along_and_the_next_call_starts_afresh(
    tmp_path,
):
    """A browser whose driver is gone says nothing of it: without the pool noticing, every
    later call of every agent would be handed the dead one until the server restarts."""
    with sites({"/": "<title>Trang</title>"}) as (site,):
        async with browsers(tmp_path / "browser", site) as pool:
            one, two = await pool.session("coach"), await pool.session("ledger")
            (pid,) = drivers()

            os.kill(pid, signal.SIGKILL)
            async with asyncio.timeout(20):
                while pool.running("coach") or pool.running("ledger"):
                    await asyncio.sleep(0.05)
            await asyncio.sleep(0.2)

            for gone in (one, two):
                with pytest.raises(OSError):
                    await asyncio.open_connection("127.0.0.1", gone.proxy.port)
            again = await pool.session("coach")
            tab = await again.tabs.open("c1")
            await tab.page.goto(site.url("/"))
            assert again is not one and await tab.page.title() == "Trang"
            assert len(drivers()) == 1 and drivers() != [pid]


class Silent:
    """A driver whose process went away: it is asked, and never answers."""

    def __init__(self) -> None:
        self.chromium, self.asked = self, 0

    async def launch_persistent_context(self, _profile: str, **_options) -> None:
        self.asked += 1
        await asyncio.Event().wait()


async def test_a_start_the_driver_never_answers_is_given_up_after_a_while(tmp_path, monkeypatch):
    # The driver's own thirty seconds come first: one that is there says what went wrong.
    assert launch_module.LAUNCH_SECONDS > 30
    monkeypatch.setattr(launch_module, "LAUNCH_SECONDS", 0.05)

    with pytest.raises(Stuck, match="Chromium did not start within 0.05 seconds"):
        async with asyncio.timeout(5):
            await launch(Silent(), tmp_path / "coach", "chromium", PROXY)


async def test_a_start_that_was_given_up_leaves_no_place_taken_and_the_next_call_starts_one(
    tmp_path, monkeypatch
):
    """A start nobody ever ended would be handed to every later call of the agent."""
    monkeypatch.setattr(launch_module, "LAUNCH_SECONDS", 0.05)
    with sites({"/": "<title>Trang</title>"}) as (site,):
        async with browsers(tmp_path / "browser", site) as pool:
            real, silent = pool.driver.get, Silent()

            async def gone_once():
                return silent if not silent.asked else await real()

            monkeypatch.setattr(pool.driver, "get", gone_once)
            with pytest.raises(Stuck):
                async with asyncio.timeout(5):
                    await pool.session("coach")
            await asyncio.sleep(0)
            assert silent.asked == 1 and not pool.in_use("coach")

            monkeypatch.setattr(launch_module, "LAUNCH_SECONDS", 40)
            tab = await (await pool.session("coach")).tabs.open("c1")
            await tab.page.goto(site.url("/"))
            assert await tab.page.title() == "Trang"


class Deaf:
    """A browser whose driver went away: asked to close, it never answers."""

    def __init__(self) -> None:
        self.asked = 0

    async def close(self) -> None:
        self.asked += 1
        await asyncio.Event().wait()


async def test_a_browser_that_never_answers_a_close_is_waited_for_only_a_while(monkeypatch, caplog):
    monkeypatch.setattr(launch_module, "CLOSE_SECONDS", 0.05)
    deaf = Deaf()

    async with asyncio.timeout(5):
        await shut_down(deaf)

    assert deaf.asked == 1
    assert "a browser did not close within 0.05 seconds" in caplog.text


async def test_a_browser_that_already_went_away_is_closed_without_a_word(caplog):
    class Dead:
        async def close(self) -> None:
            raise RuntimeError("Target page, context or browser has been closed")

    await shut_down(Dead())

    assert caplog.text == ""
