"""The client of the desktop helper: one line out, one line back, and every way that can go
wrong leaving as one error with a code."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path

import pytest

from my_agent_crew.desktop import client as client_module
from my_agent_crew.desktop.client import (
    ABSENT,
    BAD_ANSWER,
    MAX_ANSWER_BYTES,
    TIMEOUT,
    UNTRUSTED,
    DesktopClient,
    DesktopError,
)
from tests.desktop_helper import PROTOCOL, VERSION, desk, listening, socket_folder


@pytest.fixture
async def helper():
    async with listening(apps=desk(), front="Notes") as fake:
        yield fake


async def refused(client: DesktopClient, cmd: str = "state", **args) -> DesktopError:
    with pytest.raises(DesktopError) as caught:
        await client.request(cmd, **args)
    return caught.value


async def test_a_request_is_one_line_with_an_id_and_the_answer_comes_back_as_fields(helper):
    answer = await DesktopClient(helper.path).request("state")

    assert (answer["version"], answer["protocol"]) == (VERSION, PROTOCOL)
    assert answer["frontmost"] == {"app": "Notes", "bundle_id": "com.apple.Notes", "pid": 501}
    (request,) = helper.requests
    assert set(request) == {"id", "cmd"} and request["cmd"] == "state"
    assert len(request["id"]) == 16 and answer["id"] == request["id"]


async def test_arguments_travel_with_the_command_and_a_none_is_left_out(helper):
    await DesktopClient(helper.path).request("screenshot", max_px=800, since=None)

    (request,) = helper.requests
    assert request["max_px"] == 800 and "since" not in request


async def test_every_request_has_an_id_of_its_own_and_a_connection_of_its_own(helper):
    client = DesktopClient(helper.path)

    await client.request("state")
    await client.request("state")

    first, second = helper.requests
    assert first["id"] != second["id"]


async def test_text_that_is_not_ascii_reaches_the_helper_as_it_was_written(helper):
    helper.fail["act"] = ("internal", "không được")

    error = await refused(DesktopClient(helper.path), "act", kind="type", text="sữa đậu nành")

    assert helper.requests[0]["text"] == "sữa đậu nành"
    assert (error.code, error.detail) == ("internal", "không được")


async def test_no_socket_at_all_is_an_absent_helper(tmp_path: Path):
    error = await refused(DesktopClient(tmp_path / "nowhere" / "sock"))

    assert error.code == ABSENT and error.detail


async def test_a_socket_nobody_listens_on_is_an_absent_helper():
    folder = socket_folder()
    try:
        left = socket.socket(socket.AF_UNIX)
        left.bind(str(folder / "sock"))
        left.close()  # the file stays; nobody accepts on it

        error = await refused(DesktopClient(folder / "sock"))
    finally:
        (folder / "sock").unlink()
        folder.rmdir()

    assert error.code == ABSENT


async def test_a_path_too_long_for_a_socket_is_an_absent_helper(tmp_path: Path):
    long = tmp_path / ("x" * 120) / "sock"
    assert len(str(long).encode()) > 103

    assert (await refused(DesktopClient(long))).code == ABSENT


async def test_a_file_that_is_no_socket_is_an_absent_helper(tmp_path: Path):
    plain = tmp_path / "sock"
    plain.write_text("not a socket", encoding="utf-8")

    assert (await refused(DesktopClient(plain))).code == ABSENT


def owned_by(monkeypatch, path: Path, uid: int, *, follow: bool) -> None:
    """Have `os.stat` (`follow`) or `os.lstat` say that `path` belongs to `uid`."""
    name = "stat" if follow else "lstat"
    real = getattr(os, name)

    def told(given, *args, **kwargs):
        found = real(given, *args, **kwargs)
        if Path(given) != path:
            return found
        fields = list(found[:10])
        fields[4] = uid
        return os.stat_result(fields)

    monkeypatch.setattr(os, name, told)


@pytest.mark.parametrize("mode", [0o720, 0o702, 0o770, 0o777])
async def test_a_socket_in_a_folder_others_may_write_in_is_not_talked_to(helper, mode):
    helper.path.parent.chmod(mode)
    try:
        error = await refused(DesktopClient(helper.path))
    finally:
        helper.path.parent.chmod(0o700)

    assert error.code == UNTRUSTED and helper.requests == []
    # The same socket, once nobody else may write beside it, is talked to.
    helper.path.parent.chmod(0o755)
    await DesktopClient(helper.path).request("state")
    assert len(helper.requests) == 1


@pytest.mark.parametrize("follow", [True, False], ids=["folder", "socket"])
async def test_a_socket_or_a_folder_of_someone_else_is_not_talked_to(helper, monkeypatch, follow):
    other = os.geteuid() + 1
    owned_by(monkeypatch, helper.path.parent if follow else helper.path, other, follow=follow)

    error = await refused(DesktopClient(helper.path))

    assert error.code == UNTRUSTED and helper.requests == []


async def test_no_one_but_this_program_s_owner_is_trusted_whatever_the_folder(helper, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 0)

    assert (await refused(DesktopClient(helper.path))).code == UNTRUSTED
    assert helper.requests == []


async def test_a_link_to_the_helper_s_socket_is_not_its_socket(helper):
    link = helper.path.parent / "link"
    link.symlink_to(helper.path)
    try:
        error = await refused(DesktopClient(link))
    finally:
        link.unlink()

    assert error.code == ABSENT and helper.requests == []


async def test_a_helper_that_never_answers_costs_one_deadline(helper):
    helper.silent = True

    error = await refused(DesktopClient(helper.path, seconds=0.05))

    assert error.code == TIMEOUT and "state" in error.detail
    assert len(helper.requests) == 1


async def test_a_call_may_carry_a_deadline_of_its_own(helper):
    helper.silent = True

    error = await refused(DesktopClient(helper.path, seconds=30), seconds=0.05)

    assert error.code == TIMEOUT


def test_the_deadline_is_ten_seconds_and_an_answer_may_be_sixty_four_mebibytes():
    assert DesktopClient(Path("/x")).seconds == 10.0
    assert DesktopClient(Path("/x")).max_bytes == MAX_ANSWER_BYTES == 64 * 1024 * 1024


async def test_a_connection_closed_without_a_word_is_no_answer(helper):
    helper.hangs_up = True

    assert (await refused(DesktopClient(helper.path))).code == BAD_ANSWER


@pytest.mark.parametrize(
    "raw",
    [
        b"not json\n",
        b"\xff\xfe\n",
        b'["a list"]\n',
        b'"words"\n',
        b'{"id": "x"}\n',
        b'{"id": "x", "ok": "yes"}\n',
        b'{"id": "x", "ok": 1}\n',
        b'{"id": "x", "ok": true',  # the helper died in the middle of its answer
        b"[" * 100_000 + b"]" * 100_000 + b"\n",  # nested deeper than a reader goes
    ],
    ids=["words", "bytes", "list", "text", "no ok", "ok as text", "ok as number", "half", "deep"],
)
async def test_a_line_that_is_not_an_answer_is_no_answer(helper, raw):
    helper.raw = raw

    assert (await refused(DesktopClient(helper.path))).code == BAD_ANSWER


async def test_a_refusal_whose_line_never_ended_is_not_believed(helper):
    # Whole as JSON, yet the helper went away before it ended the line: nothing says that
    # what arrived was all of it.
    helper.raw = b'{"id": "", "ok": false, "error": "locked", "detail": ""}'

    error = await refused(DesktopClient(helper.path))

    assert error.code == BAD_ANSWER and "closed the connection" in error.detail


async def test_an_answer_under_another_id_is_not_ours(helper):
    helper.other_id = True

    error = await refused(DesktopClient(helper.path))

    assert error.code == BAD_ANSWER


async def test_a_refusal_under_another_id_is_not_ours_either(helper):
    helper.other_id = True
    helper.fail["state"] = ("locked", "")

    assert (await refused(DesktopClient(helper.path))).code == BAD_ANSWER


async def test_a_success_without_an_id_is_not_ours(helper):
    helper.raw = b'{"id": "", "ok": true, "version": "9"}\n'

    assert (await refused(DesktopClient(helper.path))).code == BAD_ANSWER


async def test_a_line_the_helper_could_not_read_is_refused_under_an_empty_id(helper):
    refusal = {"id": "", "ok": False, "error": "bad_request", "detail": "the line is too long"}
    helper.raw = json.dumps(refusal).encode() + b"\n"

    error = await refused(DesktopClient(helper.path))

    assert (error.code, error.detail) == ("bad_request", "the line is too long")


@pytest.mark.parametrize(
    "code",
    [
        "bad_request",
        "unknown_command",
        "locked",
        "display_asleep",
        "permission_missing:screen",
        "permission_missing:accessibility",
        "frame_mismatch",
        "app_not_running",
        "app_mismatch",
        "ref_unknown",
        "secure_input",
        "blocked_keys",
        "capture_failed",
        "internal",
    ],
)
async def test_a_refusal_leaves_with_the_code_and_the_words_of_the_helper(helper, code):
    helper.fail["state"] = (code, "why it is so")

    error = await refused(DesktopClient(helper.path))

    assert (error.code, error.detail) == (code, "why it is so")
    assert str(error) == f"{code}: why it is so"


@pytest.mark.parametrize(
    "refusal",
    [
        {"ok": False},
        {"ok": False, "error": ""},
        {"ok": False, "error": 7},
        {"ok": False, "error": "locked", "detail": ["a", "list"]},
    ],
)
async def test_a_refusal_that_names_no_error_is_no_answer(helper, refusal):
    helper.raw = json.dumps({"id": "", **refusal}).encode() + b"\n"

    assert (await refused(DesktopClient(helper.path))).code == BAD_ANSWER


async def test_a_long_detail_is_cut(helper):
    helper.fail["state"] = ("internal", "x" * 5000)

    error = await refused(DesktopClient(helper.path))

    assert len(error.detail) == client_module.DETAIL_CHARS


async def test_an_answer_over_the_cap_is_given_up_not_read(helper):
    helper.raw = b'{"id": "x", "ok": true, "png_base64": "' + b"A" * 9000 + b'"}\n'

    error = await refused(DesktopClient(helper.path, max_bytes=4000))

    assert error.code == BAD_ANSWER and "4000" in error.detail


async def test_an_answer_far_larger_than_a_default_stream_is_read_whole(helper):
    helper.scripted["screenshot"] = [{"frame_id": "f", "png_base64": "A" * 300_000}]

    answer = await DesktopClient(helper.path).request("screenshot")

    assert len(answer["png_base64"]) == 300_000


async def test_the_helper_s_folder_is_gone_once_it_stopped():
    async with listening() as fake:
        folder = fake.folder
        assert fake.path.exists() and str(folder).startswith("/tmp/")
        assert len(str(fake.path).encode()) <= 103

    assert not folder.exists()
