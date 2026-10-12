"""A number a save writes is the number the next start reads.

`agent.yaml` is written by a library that goes by YAML 1.2 and shows a float the way Python
does: `1e-05`, `1e+16`. The start's reader goes by YAML 1.1, to which a float has a dot in
it, and read those back as text. The look at the file to be then refused the save: a cost
cap of 0.00001 could not be set from the web at all.

The writer is not told which key holds a number, so it is held for every key the code's
own tables name: of a profile, of a schedule's row, of the Telegram block and of an MCP
server's entry in `config.yaml`, which the same writer writes back.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml as boot_reader
from fastapi.testclient import TestClient

from my_agent_crew import texts
from my_agent_crew.agents.channels import TELEGRAM_KEYS
from my_agent_crew.agents.profile import PROFILE_KEYS
from my_agent_crew.agents.profile_write import _yaml, as_text
from my_agent_crew.agents.profile_yaml import read_profile
from my_agent_crew.agents.schedule import SCHEDULE_KEYS
from my_agent_crew.config import load_settings
from my_agent_crew.mcp.config_parse import SERVER_KEYS, parse_servers
from my_agent_crew.server.credential_catalog import KNOWN
from tests.test_api_agents_save_matches_start import apart, crew

INF, NAN = float("inf"), float("nan")
# The numbers of the report: Python shows the first three with an exponent and no dot.
ASKED = [0.00001, 1e-7, 1e16, 1.5e300, 0.1, 3.0]
# The ends of what a float can be, and where Python goes over to the exponent.
ENDS = [5e-324, 2.2250738585072014e-308, 1.7976931348623157e308, 1e22, 1e15, 0.0001, 1.2e-9]
# Every digit a float has. Read from a file and written back, the library cut the last of
# them off where it should have rounded: the number of the second save was another one, or
# the same one in other digits.
LONG = [
    -1.989032661366619e244,
    5.249822308814304e-77,
    9.952684009002448e-208,
    -7.939416668807721e33,
    1.3647584518757569e-192,
    1e-320,
]
NUMBERS = ASKED + [-number for number in ASKED] + ENDS + LONG + [0.0, -0.0]
# No number, which each key's own check answers for and the writer has always written.
NOT_FINITE = [INF, -INF, NAN]
# One shown with an exponent beside one of its kind shown without: a key's own check tells
# the two apart by nothing.
ALIKE = [(0.00001, 0.0001), (1e-7, 0.0001), (1e16, 1e15)]

ROW = {"id": "sang", "cron": "0 7 * * *", "prompt": "Chào buổi sáng"}
CHAT = {"token_env": "BOT_TOKEN_OF_THE_TEST", "chat_id": 42}
SERVER = {"url": "https://mcp.example.com/mcp"}
# Each table of the code, and a file that holds one key of it.
PLACES: dict[str, tuple[Any, Callable[[str, Any], dict[str, Any]]]] = {
    "profile": (PROFILE_KEYS, lambda key, value: {key: value}),
    "schedule": (SCHEDULE_KEYS, lambda key, value: {"schedules": [ROW | {key: value}]}),
    "telegram": (TELEGRAM_KEYS, lambda key, value: {"telegram": CHAT | {key: value}}),
    "mcp entry": (
        SERVER_KEYS,
        lambda key, value: {"mcp_servers": {"notes": SERVER | {key: value}}},
    ),
}
KEYS = [(place, key) for place, (keys, _) in PLACES.items() for key in sorted(keys)]
OF_AN_AGENT = [(place, key) for place, key in KEYS if place != "mcp entry"]
HAND_WRITTEN = """\
# Người viết tay tệp này.
name: Thợ mã   # tên gọi
description: Viết mã
"""


def holding(place: str, key: str, value: Any) -> dict[str, Any]:
    return PLACES[place][1](key, value)


def held(place: str, key: str, data: Any) -> Any:
    """The value back out of a file `holding` made, or of what a reader made of one."""
    inner = {"profile": lambda: data, "schedule": lambda: data["schedules"][0]}
    inner |= {
        "telegram": lambda: data["telegram"],
        "mcp entry": lambda: data["mcp_servers"]["notes"],
    }
    return inner[place]()[key]


def the_start_reads(data: Any) -> Any:
    return boot_reader.safe_load(as_text(data))


def named(pair: tuple[str, str]) -> str:
    return f"{pair[0]} {pair[1]}"


@pytest.mark.parametrize(("place", "key"), KEYS, ids=map(named, KEYS))
def test_a_float_under_any_key_is_written_as_the_float_the_start_reads(
    place: str, key: str
) -> None:
    """Shown as Python shows it, which tells a float from a whole number and from a text,
    and one zero from the other."""
    read = [held(place, key, the_start_reads(holding(place, key, value))) for value in NUMBERS]

    assert [repr(got) for got in read] == [repr(value) for value in NUMBERS]


@pytest.mark.parametrize(("place", "key"), KEYS, ids=map(named, KEYS))
def test_a_float_set_in_a_file_a_person_wrote_leaves_the_rest_as_written(
    place: str, key: str
) -> None:
    kept = [line for line in HAND_WRITTEN.splitlines() if not line.startswith(f"{key}:")]
    for value in NUMBERS:
        raw = _yaml().load(HAND_WRITTEN)
        raw.update(holding(place, key, value))

        written = as_text(raw)

        assert [line for line in written.splitlines() if line in kept] == kept
        assert written.count("# tên gọi") == 1
        assert repr(held(place, key, boot_reader.safe_load(written))) == repr(value)


@pytest.mark.parametrize("value", NUMBERS, ids=repr)
def test_a_float_written_once_is_written_the_same_the_next_time(value: float) -> None:
    """The file of a second save is read by the writer's own library first."""
    once = as_text({"cost_cap_usd": value})

    again = as_text(_yaml().load(once))

    assert again == once
    assert repr(boot_reader.safe_load(again)["cost_cap_usd"]) == repr(value)


def test_what_is_no_number_is_written_as_it_always_was() -> None:
    assert as_text({"up": INF, "down": -INF, "none": NAN}) == "up: .inf\ndown: -.inf\nnone: .nan\n"


def test_a_number_too_large_to_be_one_is_written_back_as_it_always_was() -> None:
    """Read from a file it is a number of the library's own kind, which the library writes
    as the word. The word is no number to check it by."""
    typed = "up: 1e400\ndown: -1.5e+400\nabove: .inf\nbelow: -.inf\nnone: .nan\n"

    written = as_text(_yaml().load(typed))

    assert written == "up: .inf\ndown: -.inf\nabove: .inf\nbelow: -.inf\nnone: .nan\n"


# The last four are as long as the text an edit's number is given, or laid out as it is but
# for the case of a letter, or hold every digit a float has.
TYPED = ["0.00001", "1.0e-05", "1e-5", "1E-5", "1e16", ".5", "5.", "+1.5", "1.5E+3", "12e03"]
TYPED += ["100e+14", "1.5E+300", "1.989032661366619e+244", "5.249822308814304e-77"]


@pytest.mark.parametrize("form", TYPED)
def test_a_number_a_person_wrote_is_left_in_the_form_it_was_written_in(form: str) -> None:
    """Some of these the start reads as text and turns into the number itself. Rewritten,
    they would be read as another thing than the file holds now, and hold up every save."""
    text = f"cost_cap_usd: {form}  # trần chi phí\n"

    assert as_text(_yaml().load(text)) == text


# Every digit a float has, laid out as no edit's number is. The library wrote another number
# back, and no text of its own holds this one: it is written as an edit's would be.
NOT_HELD = ["19.89032661366619e+243", "198.9032661366619E+242", "0.5249822308814304e-76"]
NOT_HELD += ["52.49822308814304e-78", "0.1989032661366619e+245"]


@pytest.mark.parametrize("form", NOT_HELD)
def test_a_number_the_library_would_write_back_as_another_is_written_as_itself(form: str) -> None:
    written = as_text(_yaml().load(f"cost_cap_usd: {form}  # trần chi phí\n"))

    assert repr(boot_reader.safe_load(written)["cost_cap_usd"]) == repr(float(form))
    assert written.endswith("  # trần chi phí\n")
    assert as_text(_yaml().load(written)) == written


def what_the_start_makes(place: str, data: dict[str, Any], folder: Path) -> str:
    """The agent or the servers a start would make of the file, or the words it stops on."""
    try:
        if place == "mcp entry":
            return repr(parse_servers(data["mcp_servers"]))
        settings = load_settings(env={"MY_AGENT_HOME": str(folder)})
        return repr(read_profile("coder", folder / "agents" / "coder", data, settings))
    except ValueError as exc:
        return f"refused: {exc}"


@pytest.mark.parametrize(("place", "key"), KEYS, ids=map(named, KEYS))
def test_the_start_makes_of_a_written_file_what_it_makes_of_what_was_saved(
    tmp_path: Path, place: str, key: str
) -> None:
    """A key's own check answers for a number that is too small, too large or none at all,
    and it answers the same once the number has been through the file."""
    unlike = []
    for value in NUMBERS + NOT_FINITE:
        saved = holding(place, key, value)
        given = what_the_start_makes(place, saved, tmp_path)
        back = what_the_start_makes(place, the_start_reads(saved), tmp_path)
        if given != back:
            unlike.append(f"{value!r}: saved makes {given[:120]}, written makes {back[:120]}")

    assert unlike == []


@pytest.mark.parametrize("value", [*NUMBERS, *NOT_FINITE], ids=repr)
def test_an_mcp_servers_wait_is_judged_the_same_once_written(value: float) -> None:
    """The one float an entry holds. Seconds above none and within the limit are kept as
    they are; every other number is refused before the file as after."""
    saved = holding("mcp entry", "timeout", value)
    kept = 0 < value <= 600

    given, back = (
        what_the_start_makes("mcp entry", data, Path()) for data in (saved, the_start_reads(saved))
    )

    assert given == back
    assert given.startswith("refused: ") is not kept
    if kept:
        assert parse_servers(the_start_reads(saved)["mcp_servers"])[0].timeout == value


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in [known.name for known in KNOWN] + ["MY_AGENT_ROUTES"]:
        monkeypatch.delenv(name, raising=False)
    home = tmp_path / "home"
    (home / "agents" / "coder" / "workspace").mkdir(parents=True)
    (home / "config.yaml").write_text("routes:\n  - fake:echo\n", encoding="utf-8")
    (home / "agents" / "coder" / "agent.yaml").write_text(HAND_WRITTEN, encoding="utf-8")
    return home


@pytest.fixture
def running(home: Path) -> Iterator[tuple[TestClient, Any, Path]]:
    client, runtime = crew(home)
    with client:
        yield client, runtime, home / "agents" / "coder" / "agent.yaml"


def not_as_written(reply: Any) -> bool:
    """Whether a save was refused for how the file to be would read, and not for what the
    edit asks."""
    words = texts.SAVE_READS_BACK_CHANGED.split("(")[0]
    return reply.status_code == 422 and words in reply.text


def patch(client: TestClient, place: str, key: str, value: Any) -> Any:
    return client.patch("/api/agents/coder", json={"profile": holding(place, key, value)})


@pytest.mark.parametrize("value", ASKED + ENDS, ids=repr)
def test_a_cost_cap_of_any_size_is_saved_and_is_the_cap_the_agent_runs_with(running, value) -> None:
    client, runtime, manifest = running

    reply = patch(client, "profile", "cost_cap_usd", value)

    assert reply.status_code == 200, reply.text
    assert runtime.agents["coder"].agent.settings.cost_cap_usd == value
    assert repr(boot_reader.safe_load(manifest.read_text("utf-8"))["cost_cap_usd"]) == repr(value)
    assert apart(runtime, manifest.parents[2]) == []


@pytest.mark.parametrize("value", [0.00001, 1e16, 5e-324, *LONG], ids=repr)
def test_a_save_after_one_that_set_a_number_is_not_held_up_by_it(running, value: float) -> None:
    """The first save of a number with every digit went through. It was the next save, of
    another key, that read the number from the file and could not write it back."""
    client, runtime, manifest = running
    assert patch(client, "profile", "cost_cap_usd", value).status_code == 200
    line = [line for line in manifest.read_text("utf-8").splitlines() if "cost_cap_usd" in line]

    reply = patch(client, "profile", "description", "Viết mã và sửa lỗi")

    assert reply.status_code == 200, reply.text
    assert [
        line for line in manifest.read_text("utf-8").splitlines() if "cost_cap_usd" in line
    ] == line
    assert runtime.agents["coder"].agent.settings.cost_cap_usd == value
    assert apart(runtime, manifest.parents[2]) == []


@pytest.mark.parametrize("form", TYPED)
def test_a_number_a_person_wrote_holds_up_no_save_and_stays_as_written(
    home: Path, form: str
) -> None:
    manifest = home / "agents" / "coder" / "agent.yaml"
    manifest.write_text(f"{HAND_WRITTEN}cost_cap_usd: {form}\n", encoding="utf-8")
    client, runtime = crew(home)

    with client:
        reply = patch(client, "profile", "description", "Viết mã và sửa lỗi")

    assert reply.status_code == 200, reply.text
    assert f"cost_cap_usd: {form}\n" in manifest.read_text("utf-8")
    assert runtime.agents["coder"].agent.settings.cost_cap_usd == float(form)
    assert apart(runtime, home) == []


@pytest.mark.parametrize("form", NOT_HELD)
def test_a_typed_number_the_library_would_change_holds_up_no_save(home: Path, form: str) -> None:
    manifest = home / "agents" / "coder" / "agent.yaml"
    manifest.write_text(f"{HAND_WRITTEN}cost_cap_usd: {form}\n", encoding="utf-8")
    client, runtime = crew(home)

    with client:
        reply = patch(client, "profile", "description", "Viết mã và sửa lỗi")

    assert reply.status_code == 200, reply.text
    assert boot_reader.safe_load(manifest.read_text("utf-8"))["cost_cap_usd"] == float(form)
    assert runtime.agents["coder"].agent.settings.cost_cap_usd == float(form)
    assert apart(runtime, home) == []


@pytest.mark.parametrize(("place", "key"), OF_AN_AGENT, ids=map(named, OF_AN_AGENT))
def test_no_float_is_refused_for_how_it_would_be_written(running, place: str, key: str) -> None:
    """Saved, or refused by the key's own check: and after either, the file reads as the
    number asked or as it did, and the crew that runs is the crew a start would bring up."""
    client, runtime, manifest = running
    answers = {}
    for value in NUMBERS:
        before = manifest.read_text("utf-8")
        reply = patch(client, place, key, value)
        answers[value] = reply.status_code

        assert reply.status_code in (200, 422), reply.text
        assert not not_as_written(reply), f"{value!r}: {reply.text}"
        if reply.status_code == 200:
            now = held(place, key, boot_reader.safe_load(manifest.read_text("utf-8")))
            assert repr(now) == repr(value)
        else:
            assert manifest.read_text("utf-8") == before
        assert apart(runtime, manifest.parents[2]) == []

    assert [answers[one] for one, _ in ALIKE] == [answers[other] for _, other in ALIKE]


def test_a_cost_cap_that_is_no_number_is_refused_and_nothing_is_changed(running) -> None:
    client, runtime, manifest = running
    cap = runtime.agents["coder"].agent.settings.cost_cap_usd

    # JSON has no word for it; the route's reader takes the one Python writes.
    reply = client.patch(
        "/api/agents/coder",
        content='{"profile": {"cost_cap_usd": NaN}}',
        headers={"content-type": "application/json"},
    )

    assert reply.status_code == 422, reply.text
    assert manifest.read_text("utf-8") == HAND_WRITTEN
    assert runtime.agents["coder"].agent.settings.cost_cap_usd == cap


def test_the_routes_saved_from_the_web_leave_the_numbers_of_the_settings_file_as_they_read(
    home: Path,
) -> None:
    """`config.yaml` goes through the same writer when the routes are saved, and nothing
    looks at what was written: a number with every digit came back one digit off."""
    config = home / "config.yaml"
    servers = "".join(
        f"  {name}:\n    url: https://{name}.example.com/mcp\n    timeout: {wait}\n"
        for name, wait in (("notes", "0.5"), ("wiki", "1.989032661366619e+2"))
    )
    cap = "cost_cap_usd: 5.249822308814304e-77\n"
    config.write_text(f"routes:\n  - fake:echo\n{cap}mcp_servers:\n{servers}", encoding="utf-8")
    client, _ = crew(home)

    with client:
        body = {"routes": [{"provider": "fake", "model": "second"}]}
        reply = client.put("/api/connections/routes", json=body)

    assert reply.status_code == 200, reply.text
    written = config.read_text("utf-8")
    assert cap in written and "    timeout: 0.5\n" in written
    settings = load_settings(env={"MY_AGENT_HOME": str(home)})
    assert settings.cost_cap_usd == 5.249822308814304e-77
    assert {server.name: server.timeout for server in settings.mcp_servers} == {
        "notes": 0.5,
        "wiki": 198.9032661366619,
    }
