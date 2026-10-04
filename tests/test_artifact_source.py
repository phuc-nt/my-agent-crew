"""Reading a workspace file for a canvas. The file is opened once, only a regular file is read
and never past its kind's cap; text must be real UTF-8 and comes back as the store will keep
it; and a refusal names the path as it was sent, never where the workspace sits on this
machine."""

from __future__ import annotations

import hashlib
import os
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from my_agent_crew.artifacts.kinds import cap_bytes
from my_agent_crew.texts import WORKSPACE_ESCAPE, WORKSPACE_IS_DIR, WORKSPACE_NOT_FOUND
from my_agent_crew.texts_canvas import (
    IMPORT_NOT_FILE,
    IMPORT_NOT_IMAGE,
    IMPORT_NOT_TEXT,
    IMPORT_TOO_LARGE,
)
from my_agent_crew.tools import artifact_source
from my_agent_crew.tools.artifact_source import SourceError, read_source

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(32))
CAP = cap_bytes("markdown")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    workspace = tmp_path / "ws"
    (workspace / "notes").mkdir(parents=True)
    (workspace / "notes" / "a.md").write_bytes(b"\xef\xbb\xbf# A\r\nb\rc\n")
    (tmp_path / "outside.md").write_text("ngoài")
    return workspace


def _refused(root: Path, path: str, kind: str = "markdown") -> tuple[int, str]:
    with pytest.raises(SourceError) as caught:
        read_source(root, path, kind)
    message = str(caught.value)
    assert str(root.resolve().parent) not in message.replace(path, ""), message
    return caught.value.status, message


def test_text_comes_back_as_the_store_will_keep_it(root: Path):
    """No byte-order mark, LF line ends, and the digest of exactly that text."""
    file = read_source(root, "notes/a.md", "markdown")
    assert (file.content, file.data, file.size) == ("# A\nb\nc\n", None, 8)
    assert file.digest == hashlib.sha256(b"# A\nb\nc\n").hexdigest()
    assert file.path == root.resolve() / "notes" / "a.md"


def test_a_picture_comes_back_byte_for_byte(root: Path):
    (root / "logo.png").write_bytes(PNG)
    file = read_source(root, "logo.png", "image")
    assert (file.content, file.data, file.size) == (None, PNG, len(PNG))
    assert file.digest == hashlib.sha256(PNG).hexdigest()


def test_a_path_out_of_the_workspace_is_refused(root: Path):
    for path in ("../outside.md", str(root.parent / "outside.md"), "~no-such-user-0/a.md"):
        assert _refused(root, path) == (403, WORKSPACE_ESCAPE), path


def test_an_absolute_path_and_a_link_inside_the_workspace_are_read(root: Path):
    """A link the person placed in the workspace is followed, as `workspace_read` follows it."""
    (root / "linked.md").symlink_to(root.parent / "outside.md")
    assert read_source(root, str(root / "notes" / "a.md"), "markdown").content == "# A\nb\nc\n"
    assert read_source(root, "linked.md", "markdown").content == "ngoài"


def test_a_file_that_is_not_there_is_not_found(root: Path):
    for path in ("missing.md", "notes/a.md/inside.md"):
        assert _refused(root, path) == (404, WORKSPACE_NOT_FOUND.format(path=path)), path


def test_a_directory_is_refused(root: Path):
    assert _refused(root, "notes") == (422, WORKSPACE_IS_DIR.format(path="notes"))


def test_a_pipe_is_refused_without_waiting_for_a_writer(root: Path):
    """Opening a pipe to read waits for a writer unless the open says not to, and a server
    thread waiting there never comes back."""
    pipe = root / "pipe.md"
    os.mkfifo(pipe)
    outcome: list[BaseException | None] = []

    def read() -> None:
        try:
            read_source(root, "pipe.md", "markdown")
            outcome.append(None)
        except BaseException as exc:
            outcome.append(exc)

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        reader.join(timeout=5)
        waited = reader.is_alive()
    finally:
        # A reader still waiting is let go by a writer, so it cannot outlive the test.
        writer = os.open(pipe, os.O_RDWR | os.O_NONBLOCK)
        reader.join(timeout=5)
        os.close(writer)
    assert not waited
    [error] = outcome
    assert isinstance(error, SourceError)
    assert (error.status, str(error)) == (422, IMPORT_NOT_FILE.format(path="pipe.md"))


def test_a_device_behind_a_link_is_refused(root: Path):
    (root / "zero.md").symlink_to("/dev/zero")
    assert _refused(root, "zero.md") == (422, IMPORT_NOT_FILE.format(path="zero.md"))


def test_a_file_over_the_cap_is_refused_before_a_byte_is_read(root: Path, monkeypatch):
    (root / "big.md").write_bytes(b"a" * (CAP + 1))

    def read(*_: object) -> bytes:
        raise AssertionError("a file over the cap was read")

    monkeypatch.setattr(artifact_source.os, "read", read)
    refusal = IMPORT_TOO_LARGE.format(path="big.md", kind="markdown", cap=CAP)
    assert _refused(root, "big.md") == (413, refusal)


def test_a_file_that_grew_after_it_was_measured_is_refused_one_byte_past_the_cap(
    root: Path, monkeypatch
):
    (root / "log.md").write_bytes(b"a" * (CAP + 4096))
    fstat, read, taken = os.fstat, os.read, []

    def measured_small(fd: int) -> SimpleNamespace:
        return SimpleNamespace(st_mode=fstat(fd).st_mode, st_size=CAP)

    def counted(fd: int, length: int) -> bytes:
        taken.append(read(fd, length))
        return taken[-1]

    monkeypatch.setattr(artifact_source.os, "fstat", measured_small)
    monkeypatch.setattr(artifact_source.os, "read", counted)
    refusal = IMPORT_TOO_LARGE.format(path="log.md", kind="markdown", cap=CAP)
    assert _refused(root, "log.md") == (413, refusal)
    assert sum(len(chunk) for chunk in taken) == CAP + 1


def test_a_file_exactly_at_the_cap_is_read_whole(root: Path):
    (root / "full.md").write_bytes(b"a" * CAP)
    assert read_source(root, "full.md", "markdown").size == CAP


@pytest.mark.parametrize("raw", [b"caf\xe9", b"\xff\xfe# A", b"# A\x00b", b"\x89PNG\r\n\x1a\n"])
def test_bytes_that_are_not_utf8_text_are_refused_rather_than_patched(root: Path, raw: bytes):
    """A byte swapped for a replacement mark would go back out as a damaged file."""
    (root / "raw.md").write_bytes(raw)
    refusal = IMPORT_NOT_TEXT.format(path="raw.md", kind="markdown")
    assert _refused(root, "raw.md") == (422, refusal)


def test_bytes_that_begin_as_no_picture_are_refused(root: Path):
    (root / "fake.png").write_bytes(b"<html>khong phai anh</html>")
    assert _refused(root, "fake.png", "image") == (422, IMPORT_NOT_IMAGE.format(path="fake.png"))
