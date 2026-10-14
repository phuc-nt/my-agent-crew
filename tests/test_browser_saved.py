"""Where a browser tool leaves a file and under what name: a name is only its plain letters
whoever chose it and ends as data does, a file is made new or not at all, and the folder is
judged where it really is and then walked to through no link."""

from __future__ import annotations

import ctypes
import logging
import os
import stat
import sys
import time

import pytest

from my_agent_crew.browser import quarantine
from my_agent_crew.browser.folder import held_bytes, keep, listed, reached, remove
from my_agent_crew.browser.saved import (
    DATA_ENDINGS,
    ENDING_CHARS,
    STEM_CHARS,
    file_name,
    inert,
    place,
)
from my_agent_crew.texts import WORKSPACE_ESCAPE, WORKSPACE_WRITE_OUTSIDE
from my_agent_crew.tools.registry import ToolError


@pytest.mark.parametrize(
    ("said", "name"),
    [
        ("hoá đơn tháng 10.pdf", "hoa-don-thang-10.pdf"),
        ("Đà Nẵng.PDF", "Da-Nang.PDF"),
        ("  bảng_lương.xlsx \n", "bang_luong.xlsx"),
        ("báo cáo (bản 2) [cuối].xlsx", "bao-cao-ban-2-cuoi.xlsx"),
        ("a\nb\tc.pdf", "a-b-c.pdf"),
        ("a.tar.gz", "a.tar.gz"),
        ("a..b", "a.b"),
        ("tep.", "tep"),
        ("khong-co-duoi", "khong-co-duoi"),
        # Only the last part of a path is a name, whichever way its slashes lean.
        ("a/b/c.txt", "c.txt"),
        ("../../etc/passwd", "passwd"),
        ("..\\..\\x.exe", "x.exe"),
        ("C:\\Users\\chu\\hoá đơn.pdf", "hoa-don.pdf"),
        # Nothing in front that hides a file or reads as an option.
        ("-rf", "rf"),
        ("--help.txt", "help.txt"),
        ("__init__.py", "init.py"),
        # A name none of whose letters could be kept, before the ending it had.
        (".bashrc", "tep.bashrc"),
        ("...pdf", "tep.pdf"),
        ("发票.pdf", "tep.pdf"),
        ("发票", "tep"),
        ("..", "tep"),
        (".", "tep"),
        ("", "tep"),
        ("   ", "tep"),
        ("a/b/", "tep"),
        ("a.-", "a"),
        ("$(rm -rf ~).sh", "rm-rf.sh"),
        ("a;b|c&d.txt", "a-b-c-d.txt"),
        ("x" * 200 + ".pdf", "x" * STEM_CHARS + ".pdf"),
        ("x" * 79 + "-yz.pdf", "x" * 79 + ".pdf"),  # no hyphen left where the name was cut
        # A long tail after the last dot is no ending: it is part of the name.
        ("." + "b" * ENDING_CHARS, "tep." + "b" * ENDING_CHARS),
        ("." + "b" * (ENDING_CHARS + 1), "b" * (ENDING_CHARS + 1)),
        ("..__.ssh_authorized_keys", "ssh_authorized_keys"),
        ("x" * 100 + "." + "b" * ENDING_CHARS, "x" * STEM_CHARS + "." + "b" * ENDING_CHARS),
        ("x" * 100 + "." + "b" * (ENDING_CHARS + 1), "x" * STEM_CHARS),
        ("a." + "b" * 30, "a." + "b" * 30),
    ],
)
def test_a_name_is_the_last_part_of_what_was_said_in_plain_letters(said, name):
    assert file_name(said, "tep") == name


@pytest.mark.parametrize(
    ("said", "name"),
    [
        ("Hoá đơn tháng 10", "Hoa-don-thang-10.pdf"),
        ("hoa-don.pdf", "hoa-don.pdf"),
        ("hoa-don.PDF", "hoa-don.pdf"),
        # Another ending is part of the name: the file is what the tool made, not what it says.
        ("a.b", "a.b.pdf"),
        ("x/y/Báo cáo Đà Nẵng.txt", "Bao-cao-Da-Nang.txt.pdf"),
        ("virus.pdf.exe", "virus.pdf.exe.pdf"),
        ("发票.pdf", "trang.pdf"),
        ("", "trang.pdf"),
        (".pdf", "trang.pdf"),
    ],
)
def test_a_name_ends_as_the_tool_says_whatever_was_said(said, name):
    assert file_name(said, "trang", "pdf") == name


@pytest.mark.parametrize(
    ("name", "kept"),
    [
        ("hoa-don.pdf", "hoa-don.pdf"),
        ("so-lieu.CSV", "so-lieu.CSV"),
        ("anh.JpEg", "anh.JpEg"),
        ("a.tar.zip", "a.tar.zip"),
        # A name a program goes looking for, or runs, or reads as instructions.
        ("conftest.py", "conftest.py.bin"),
        ("Makefile", "Makefile.bin"),
        ("CLAUDE.md", "CLAUDE.md.bin"),
        ("install.pkg", "install.pkg.bin"),
        ("authorized_keys", "authorized_keys.bin"),
        ("hoa-don.pdf.exe", "hoa-don.pdf.exe.bin"),
        ("a.html", "a.html.bin"),
        ("a.svg", "a.svg.bin"),
        ("pdf", "pdf.bin"),  # a word, not an ending
        ("download", "download.bin"),
        ("tep.bin", "tep.bin"),  # as it would be made
    ],
)
def test_a_name_that_does_not_end_as_data_does_ends_in_bin(name, kept):
    assert inert(name) == kept
    assert inert(kept) == kept  # said once, never twice


def test_the_endings_of_data_are_a_short_list_and_what_a_tool_makes_is_on_it():
    listed = "pdf csv tsv txt json xml xlsx xls docx doc pptx ppt zip png jpg jpeg gif webp"
    assert DATA_ENDINGS == frozenset(listed.split())
    assert inert(file_name("../x.exe", "page", "pdf")) == "x.exe.pdf"


def test_a_file_is_made_in_a_folder_that_is_made_for_it(tmp_path):
    kept = keep(tmp_path, "a/downloads", "hoa-don.pdf", b"%PDF-1.4 x")

    assert kept == ("hoa-don.pdf", 10)
    assert (tmp_path / "a" / "downloads" / "hoa-don.pdf").read_bytes() == b"%PDF-1.4 x"
    assert stat.S_IMODE((tmp_path / "a" / "downloads" / "hoa-don.pdf").stat().st_mode) == 0o644


def test_a_file_is_copied_whole_from_the_file_that_holds_it(tmp_path):
    held = tmp_path / "held"
    held.write_bytes(b"k" * 300_000)

    kept = keep(tmp_path, "downloads", "tep.bin", held)

    assert kept == ("tep.bin", 300_000)
    assert (tmp_path / "downloads" / "tep.bin").read_bytes() == b"k" * 300_000
    assert held.read_bytes() == b"k" * 300_000  # the source is its owner's to remove


def test_a_name_that_is_taken_gets_a_number_and_nothing_is_written_over(tmp_path):
    def kept(name: str, data: bytes) -> str:
        return keep(tmp_path, "d", name, data)[0]

    numbered = [kept("hoa-don.pdf", data) for data in (b"mot", b"hai", b"ba")]
    bare = [kept("khong-duoi", data) for data in (b"x", b"y")]
    two_dots = [kept("a.tar.gz", data) for data in (b"x", b"y")]

    assert numbered == ["hoa-don.pdf", "hoa-don-2.pdf", "hoa-don-3.pdf"]
    assert [(tmp_path / "d" / name).read_bytes() for name in numbered] == [b"mot", b"hai", b"ba"]
    assert bare == ["khong-duoi", "khong-duoi-2"]
    assert two_dots == ["a.tar.gz", "a.tar-2.gz"]


def test_a_link_already_under_the_name_is_never_written_through(tmp_path):
    folder, outside = tmp_path / "downloads", tmp_path / "outside"
    folder.mkdir()
    outside.mkdir()
    (outside / "theirs.txt").write_bytes(b"theirs")
    os.symlink(outside / "theirs.txt", folder / "a.txt")  # to a file that is there
    os.symlink(outside / "new.txt", folder / "b.txt")  # to one that would be made
    os.symlink(outside, folder / "c.txt")  # to a folder

    made = [keep(tmp_path, "downloads", name, b"ours")[0] for name in ("a.txt", "b.txt", "c.txt")]

    assert made == ["a-2.txt", "b-2.txt", "c-2.txt"]
    assert (outside / "theirs.txt").read_bytes() == b"theirs"
    assert sorted(p.name for p in outside.iterdir()) == ["theirs.txt"]


def test_a_file_that_could_not_be_written_whole_is_taken_away_again(tmp_path):
    folder = tmp_path / "downloads"
    keep(tmp_path, "downloads", "a.bin", b"kept")

    with pytest.raises(FileNotFoundError):
        keep(tmp_path, "downloads", "b.bin", tmp_path / "gone")
    with pytest.raises(IsADirectoryError):
        keep(tmp_path, "downloads", "a.bin", tmp_path)

    assert [(p.name, p.read_bytes()) for p in folder.iterdir()] == [("a.bin", b"kept")]


def test_a_folder_that_cannot_be_made_takes_no_file(tmp_path):
    (tmp_path / "downloads").write_bytes(b"a file where the folder would be")

    with pytest.raises(FileExistsError) as error:
        keep(tmp_path, "downloads", "a.bin", b"x")

    assert error.value.strerror == "File exists"
    assert (tmp_path / "downloads").read_bytes() == b"a file where the folder would be"


@pytest.mark.parametrize(
    ("write_paths", "planted"),
    [((), "downloads"), (("data",), "data/downloads"), (("data",), "data")],
)
def test_a_folder_that_became_a_link_after_it_was_judged_takes_no_file(
    tmp_path, write_paths, planted
):
    workspace, outside = tmp_path / "ws", tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    shown = place(workspace, write_paths, "downloads")[1]  # judged: nothing is in the way yet
    (workspace / planted).parent.mkdir(exist_ok=True)
    os.symlink(outside, workspace / planted)

    with pytest.raises(ToolError) as error:
        keep(workspace, shown, "hoa-don.pdf", b"%PDF-1.4 x")

    assert str(error.value) == WORKSPACE_ESCAPE
    assert list(outside.iterdir()) == []  # no file, and no folder made for one


def test_a_link_to_another_of_the_workspace_s_folders_is_no_folder_to_walk_through(tmp_path):
    workspace = tmp_path / "ws"
    (workspace / "src").mkdir(parents=True)
    shown = place(workspace, (), "downloads")[1]
    os.symlink(workspace / "src", workspace / "downloads")

    with pytest.raises(ToolError) as error:
        keep(workspace, shown, "hoa-don.pdf", b"x")

    # Judged afresh it is where the link leads, and the answer would name that place.
    assert str(error.value) == WORKSPACE_ESCAPE and list((workspace / "src").iterdir()) == []
    assert place(workspace, (), "downloads")[1] == "src"


@pytest.mark.parametrize("shown", ["../outside", "a/../../outside", "/outside", "//outside"])
def test_a_walk_never_leaves_the_folder_it_began_in(tmp_path, shown):
    workspace = tmp_path / "ws"
    workspace.mkdir()

    with pytest.raises(ToolError) as error:
        keep(workspace, shown.replace("/outside", f"{tmp_path}/outside", 1), "a.pdf", b"x")

    assert str(error.value) == WORKSPACE_ESCAPE
    assert [p.name for p in tmp_path.iterdir()] == ["ws"] and list(workspace.iterdir()) == []


def test_a_workspace_reached_by_a_link_is_written_where_it_really_is(tmp_path):
    (tmp_path / "real").mkdir()
    os.symlink(tmp_path / "real", tmp_path / "alias")

    assert keep(tmp_path / "alias", "downloads", "a.pdf", b"x") == ("a.pdf", 1)
    assert (tmp_path / "real" / "downloads" / "a.pdf").read_bytes() == b"x"


def test_no_descriptor_is_left_open_whether_a_file_was_kept_or_not(tmp_path):
    def open_now() -> int:
        return len(os.listdir("/dev/fd"))

    workspace, outside = tmp_path / "ws", tmp_path / "outside"
    (workspace / "a").mkdir(parents=True)
    outside.mkdir()
    os.symlink(outside, workspace / "a" / "linked")
    (workspace / "a" / "taken").write_bytes(b"a file")
    before = open_now()

    keep(workspace, "a/b/downloads", "a.pdf", b"x")
    assert held_bytes(workspace, "a/b/downloads") == 1
    with reached(workspace, "a/b/downloads") as folder:
        assert [name for name, _found in listed(folder)] == ["a.pdf"]
        remove(folder, "a.pdf")
        remove(folder, "a.pdf")  # gone already: no trouble
    for shown, error in (("a/linked/x", ToolError), ("a/taken/x", FileExistsError)):
        with pytest.raises(error):
            keep(workspace, shown, "a.pdf", b"x")
    with pytest.raises(FileNotFoundError):
        keep(workspace, "a/b", "b.pdf", tmp_path / "gone")

    assert open_now() == before
    assert list((workspace / "a" / "b" / "downloads").iterdir()) == []


def test_what_a_folder_holds_is_the_files_directly_in_it(tmp_path):
    workspace, outside = tmp_path / "ws", tmp_path / "outside"
    folder = workspace / "data" / "downloads"
    (folder / "con").mkdir(parents=True)
    outside.mkdir()
    (outside / "lon.pdf").write_bytes(b"x" * 9000)
    (folder / "a.pdf").write_bytes(b"x" * 700)
    (folder / "b.csv").write_bytes(b"x" * 300)
    (folder / "con" / "sau.pdf").write_bytes(b"x" * 5000)  # further down: not counted
    os.symlink(outside / "lon.pdf", folder / "lien-ket.pdf")  # what a link names: not counted
    os.symlink(outside, folder / "thu-muc")

    assert held_bytes(workspace, "data/downloads") == 1000
    assert held_bytes(workspace, "data/con") == 0  # not there, and not made by asking
    assert not (workspace / "data" / "con").exists()
    assert held_bytes(workspace, "data/downloads/a.pdf") == 0  # a file is no folder
    with pytest.raises(ToolError) as error:
        held_bytes(workspace, "data/downloads/thu-muc")
    assert str(error.value) == WORKSPACE_ESCAPE


def quarantine_of(path) -> bytes | None:
    """The mark macOS keeps on the file at `path`, read back as the system holds it."""
    libc = ctypes.CDLL(None, use_errno=True)
    libc.getxattr.restype = ctypes.c_ssize_t
    libc.getxattr.argtypes = [
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_uint32,
        ctypes.c_int,
    ]
    held = ctypes.create_string_buffer(256)
    size = libc.getxattr(os.fsencode(path), quarantine.NAME, held, len(held), 0, 0)
    return held.raw[:size] if size >= 0 else None


@pytest.mark.skipif(sys.platform != "darwin", reason="the mark is macOS's own")
def test_a_kept_file_carries_the_mark_of_a_file_that_came_from_outside(tmp_path):
    held = tmp_path / "held"
    held.write_bytes(b"k" * 2000)
    before = int(time.time())

    keep(tmp_path, "downloads", "a.bin", b"written")
    keep(tmp_path, "downloads", "b.bin", held)

    for name in ("a.bin", "b.bin"):
        carried = quarantine_of(tmp_path / "downloads" / name)
        assert carried is not None, f"{name} carries no mark"
        flags, at, who, rest = carried.decode().split(";")
        assert (flags, who, rest) == ("0081", "my-agent-crew", "")
        assert before <= int(at, 16) <= int(time.time())
    assert quarantine_of(held) is None  # a file nobody marked carries none


@pytest.mark.skipif(sys.platform != "darwin", reason="the mark is macOS's own")
def test_a_mark_that_could_not_be_put_is_noted_and_fails_nothing(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger=quarantine.__name__)
    closed = os.open(tmp_path, os.O_RDONLY)
    os.close(closed)

    quarantine.mark(closed)  # no file is open under that number any more

    (noted,) = caplog.records
    assert noted.levelno == logging.DEBUG and "Bad file descriptor" in noted.getMessage()


def test_elsewhere_than_macos_there_is_no_mark_and_nothing_is_done(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger=quarantine.__name__)

    quarantine.mark(-1, platform="linux")  # a number that is no file: it is never looked at

    assert caplog.records == []


def test_the_folder_is_the_workspace_s_or_the_first_an_agent_is_held_to(tmp_path):
    workspace = tmp_path / "ws"
    (workspace / "data").mkdir(parents=True)
    real = os.path.realpath(workspace)

    assert place(workspace, (), "downloads") == (type(workspace)(real) / "downloads", "downloads")
    assert place(workspace, ("data", "notes"), "downloads") == (
        type(workspace)(real) / "data" / "downloads",
        "data/downloads",
    )
    assert not (workspace / "downloads").exists()  # naming a place makes nothing


def test_a_folder_a_link_leads_out_of_the_workspace_takes_no_file(tmp_path):
    workspace, outside = tmp_path / "ws", tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    os.symlink(outside, workspace / "downloads")

    with pytest.raises(ToolError) as error:
        place(workspace, (), "downloads")

    assert str(error.value) == WORKSPACE_ESCAPE


def test_a_folder_a_link_leads_out_of_an_agent_s_folders_takes_no_file(tmp_path):
    workspace = tmp_path / "ws"
    (workspace / "data").mkdir(parents=True)
    (workspace / "src").mkdir()
    os.symlink(workspace / "src", workspace / "data" / "downloads")

    with pytest.raises(ToolError) as error:
        place(workspace, ("data", "notes"), "downloads")

    assert str(error.value) == WORKSPACE_WRITE_OUTSIDE.format(
        paths="data, notes", path="data/downloads"
    )
    # A folder held to may itself be a link to another of the agent's folders.
    os.symlink(workspace / "data", workspace / "notes")
    assert place(workspace, ("notes",), "shots")[1] == "data/shots"
