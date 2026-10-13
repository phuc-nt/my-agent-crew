"""Where an agent's browser may still be signed in: which cookies count, what of them is kept
and what never is, what is written when a browser closes and read when none is up, and what a
person is shown of it."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import pytest

from my_agent_crew.browser import logins
from my_agent_crew.browser.logins import FILE, TOLD, kept, read, recalled, remember, told
from my_agent_crew.config_browser import profile_dir
from tests.browser_servers import Site, browsers

NOW = 1_800_000_000.0
LATER = NOW + 3_600


def cookie(domain: str = "shop.example", expires: float = LATER, **own: Any) -> dict[str, Any]:
    signed_in = {"name": "session", "value": "bi-mat-123", "path": "/", "secure": True}
    return {**signed_in, "domain": domain, "expires": expires, "httpOnly": True, **own} | {
        "sameSite": own.get("sameSite", "Lax")
    }


class Context:
    """A browser that tells its cookies, late or not at all."""

    def __init__(self, cookies: list[dict[str, Any]] | Exception, after: float = 0.0) -> None:
        self.answer, self.after = cookies, after

    async def cookies(self) -> list[dict[str, Any]]:
        await asyncio.sleep(self.after)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_a_cookie_counts_when_no_script_reads_it_it_outlasts_the_browser_and_stays_on_its_site():
    assert kept([cookie()], NOW) == {"shop.example": LATER}
    assert kept([cookie(sameSite="Strict")], NOW) == {"shop.example": LATER}
    # One a script on the page can read is how a page remembers a choice, not a person.
    assert kept([cookie(httpOnly=False)], NOW) == {}
    # One that is sent along to other sites is how an advertiser follows a person.
    assert kept([cookie(sameSite="None")], NOW) == {}
    # One that ends with the browser says -1; one that ran out is no sign of anything.
    assert kept([cookie(expires=-1)], NOW) == {}
    assert kept([cookie(expires=NOW)], NOW) == {}
    assert kept([cookie(expires=NOW + 1)], NOW) == {"shop.example": NOW + 1}
    # And one that says nothing usable of itself is passed over.
    for broken in ({"domain": ""}, {"domain": None}, {"expires": None}, {"expires": "mai"}):
        assert kept([cookie(**broken)], NOW) == {}, broken
    assert kept([{"name": "x"}], NOW) == {}


def test_a_host_is_kept_once_in_small_letters_with_the_last_moment_any_of_its_cookies_runs_out():
    found = kept(
        [
            cookie(".Shop.Example", NOW + 10),
            cookie("shop.example", NOW + 500),
            cookie("shop.example", NOW + 50),
            cookie("pay.shop.example", NOW + 7),
            cookie("ads.example", NOW + 900, sameSite="None"),
        ],
        NOW,
    )

    assert found == {"shop.example": NOW + 500, "pay.shop.example": NOW + 7}
    assert all(type(until) is float for until in found.values())


async def test_only_the_host_and_the_moment_are_ever_taken_of_a_cookie(tmp_path: Path):
    # A browser is judged by the clock on the wall, so these run out an hour from the run.
    soon = time.time() + 3_600
    other = cookie("bank.example", soon + 5, name="sid", value="rat-bi-mat")
    browser = Context([cookie(expires=soon), other])

    found = await read(browser)
    await remember(browser, tmp_path)

    assert found == {"shop.example": soon, "bank.example": soon + 5}
    assert recalled(tmp_path) == found
    written = (tmp_path / FILE).read_text()
    assert json.loads(written).keys() == {"hosts"}
    assert json.loads(written)["hosts"].keys() == {"shop.example", "bank.example"}
    for secret in ("session", "bi-mat-123", "sid", "rat-bi-mat", "secure", "path"):
        assert secret not in written and secret not in repr(found), secret
    # Nobody but the owner reads even that, and nothing half written is left beside it.
    assert (tmp_path / FILE).stat().st_mode & 0o777 == 0o600
    assert [path.name for path in tmp_path.iterdir()] == [FILE]


async def test_a_browser_that_will_not_say_tells_nothing_and_leaves_what_was_written(
    tmp_path: Path, monkeypatch
):
    assert logins.READ_SECONDS == 2.0
    monkeypatch.setattr(logins, "READ_SECONDS", 0.05)
    until = time.time() + 3_600
    await remember(Context([cookie(expires=until)]), tmp_path)

    for silent in (Context(RuntimeError("Target closed")), Context([cookie()], after=30)):
        assert await read(silent) is None
        await remember(silent, tmp_path)
        assert recalled(tmp_path) == {"shop.example": until}

    # A browser with no cookie that counts did say: what was written before is no longer so.
    await remember(Context([cookie(httpOnly=False)]), tmp_path)
    assert recalled(tmp_path) == {}


async def test_of_a_browser_that_will_not_say_what_it_was_last_seen_to_hold_is_written(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(logins, "READ_SECONDS", 0.05)
    soon = time.time() + 3_600
    seen = {"shop.example": soon}

    for silent in (Context(RuntimeError("Target closed")), Context([cookie()], after=30)):
        await remember(silent, tmp_path, seen)
        assert recalled(tmp_path) == seen
        (tmp_path / FILE).unlink()

    # One that does say is believed over what was seen of it a moment before.
    await remember(Context([cookie("bank.example", soon + 9)]), tmp_path, seen)
    assert recalled(tmp_path) == {"bank.example": soon + 9}
    await remember(Context([]), tmp_path, seen)
    assert recalled(tmp_path) == {}
    # And what was seen of a browser whose profile nobody named is written nowhere.
    (tmp_path / FILE).unlink()
    await remember(Context(RuntimeError("Target closed")), None, seen)
    assert list(tmp_path.iterdir()) == []


async def test_a_browser_with_no_profile_named_writes_nothing_and_is_not_asked(tmp_path: Path):
    def never() -> None:
        raise AssertionError("a browser whose profile nobody named is not asked")

    browser = Context([cookie()])
    browser.cookies = never

    await remember(browser, None)

    assert list(tmp_path.iterdir()) == []


async def test_a_profile_that_cannot_be_written_to_is_logged_and_stops_nothing(
    tmp_path: Path, caplog
):
    gone = tmp_path / "no-such-profile"

    await remember(Context([cookie(expires=time.time() + 60)]), gone)

    assert "was not written" in caplog.text and "bi-mat-123" not in caplog.text
    assert recalled(gone) is None


@pytest.mark.parametrize(
    "written",
    [None, "", "{", "[]", '{"hosts": 3}', '{"hosts": {"a": "mai"}}', '{"other": {}}', "null"],
)
def test_nothing_is_recalled_of_a_profile_no_browser_closed_on_or_of_a_file_that_is_no_such(
    tmp_path: Path, written: str | None
):
    if written is not None:
        (tmp_path / FILE).write_text(written)

    assert recalled(tmp_path) is None


def test_an_agent_with_hosts_of_its_own_is_told_of_each_of_them_also_one_that_holds_nothing():
    held = {
        "shop.example": NOW + 100,
        "pay.shop.example": NOW + 900,
        "elsewhere.test": NOW + 5_000,  # no host of the agent's is under it or over it
        "other.example": NOW + 9_000,
        "old.example": NOW - 1,
    }
    own = ("shop.example", "*.shop.example", "www.shop.example", "old.example", "new.example")

    shown = told(held, own, NOW)

    at = "2027-01-15T08:{}+00:00".format
    assert shown == [
        # Its own cookie, and what a page under it set.
        {"host": "shop.example", "until": at("15:00")},
        {"host": "*.shop.example", "until": at("15:00")},
        # A page there is sent the cookie of the host above it.
        {"host": "www.shop.example", "until": at("01:40")},
        {"host": "old.example", "until": None},
        {"host": "new.example", "until": None},
    ]


def test_a_host_that_only_ends_alike_is_not_under_another():
    held = {"notshop.example": LATER, "shop.example.evil.test": LATER}

    assert told(held, ("shop.example", "*.shop.example"), NOW) == [
        {"host": "shop.example", "until": None},
        {"host": "*.shop.example", "until": None},
    ]


def test_an_agent_with_no_hosts_of_its_own_is_told_of_the_hosts_that_hold_something_by_name():
    held = {"b.example": NOW + 60, "a.example": NOW + 120, "gone.example": NOW}

    assert told(held, (), NOW) == [
        {"host": "a.example", "until": "2027-01-15T08:02:00+00:00"},
        {"host": "b.example", "until": "2027-01-15T08:01:00+00:00"},
    ]
    assert told({}, (), NOW) == []
    many = {f"h{n:03}.example": LATER for n in range(TOLD + 7)}
    assert [row["host"] for row in told(many, (), NOW)] == sorted(many)[:TOLD] and TOLD == 50


SIGNS_IN = {
    "/": lambda site: (
        200,
        {
            "set-cookie": "session=bi-mat-123; Max-Age=3600; HttpOnly; SameSite=Lax; Path=/",
            "cache-control": "no-store",
        },
        "<title>Đã vào</title><script>document.cookie='theme=toi; max-age=3600'</script>ok",
    )
}


async def test_what_a_browser_holds_is_written_beside_its_profile_each_time_it_closes(tmp_path):
    site = Site(SIGNS_IN)
    try:
        async with browsers(tmp_path, site) as pool:
            profile = profile_dir(pool.root, "coach")
            session = await pool.session("coach")
            assert session.profile == profile and recalled(profile) is None
            page = await session.context.new_page()
            await page.goto(site.url("/"))
            before = time.time()

            live = await read(session.context)
            assert await pool.stop("coach") is True

            written = recalled(profile)
            assert written == live and written.keys() == {"127.0.0.1"}
            assert before + 3_500 < written["127.0.0.1"] < time.time() + 3_700
            assert "bi-mat-123" not in (profile / FILE).read_text()
            # The next browser on the profile is still signed in, and says the same.
            again = await pool.session("coach")
            assert (await read(again.context)).keys() == {"127.0.0.1"}
    finally:
        site.close()
