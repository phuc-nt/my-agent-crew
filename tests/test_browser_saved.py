"""Where a browser tool leaves a file and under what name: a name is only its plain letters
whoever chose it, a file is made new or not at all, and the folder is judged where it really
is."""

from __future__ import annotations

import os

import pytest

from my_agent_crew.browser.saved import ENDING_CHARS, STEM_CHARS, file_name, keep, place
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


def test_a_file_is_made_in_a_folder_that_is_made_for_it(tmp_path):
    folder = tmp_path / "a" / "downloads"

    path = keep(folder, "hoa-don.pdf", b"%PDF-1.4 x")

    assert path == folder / "hoa-don.pdf" and path.read_bytes() == b"%PDF-1.4 x"


def test_a_file_is_copied_whole_from_the_file_that_holds_it(tmp_path):
    held = tmp_path / "held"
    held.write_bytes(b"k" * 300_000)

    path = keep(tmp_path / "downloads", "tep.bin", held)

    assert path.read_bytes() == b"k" * 300_000
    assert held.read_bytes() == b"k" * 300_000  # the source is its owner's to remove


def test_a_name_that_is_taken_gets_a_number_and_nothing_is_written_over(tmp_path):
    first = keep(tmp_path, "hoa-don.pdf", b"mot")
    second = keep(tmp_path, "hoa-don.pdf", b"hai")
    third = keep(tmp_path, "hoa-don.pdf", b"ba")
    bare = [keep(tmp_path, "khong-duoi", data) for data in (b"x", b"y")]
    two_dots = [keep(tmp_path, "a.tar.gz", data) for data in (b"x", b"y")]

    assert [p.name for p in (first, second, third)] == [
        "hoa-don.pdf",
        "hoa-don-2.pdf",
        "hoa-don-3.pdf",
    ]
    assert [p.read_bytes() for p in (first, second, third)] == [b"mot", b"hai", b"ba"]
    assert [p.name for p in bare] == ["khong-duoi", "khong-duoi-2"]
    assert [p.name for p in two_dots] == ["a.tar.gz", "a.tar-2.gz"]


def test_a_link_already_under_the_name_is_never_written_through(tmp_path):
    folder, outside = tmp_path / "downloads", tmp_path / "outside"
    folder.mkdir()
    outside.mkdir()
    (outside / "theirs.txt").write_bytes(b"theirs")
    os.symlink(outside / "theirs.txt", folder / "a.txt")  # to a file that is there
    os.symlink(outside / "new.txt", folder / "b.txt")  # to one that would be made
    os.symlink(outside, folder / "c.txt")  # to a folder

    made = [keep(folder, name, b"ours") for name in ("a.txt", "b.txt", "c.txt")]

    assert [p.name for p in made] == ["a-2.txt", "b-2.txt", "c-2.txt"]
    assert (outside / "theirs.txt").read_bytes() == b"theirs"
    assert sorted(p.name for p in outside.iterdir()) == ["theirs.txt"]


def test_a_file_that_could_not_be_written_whole_is_taken_away_again(tmp_path):
    folder = tmp_path / "downloads"
    keep(folder, "a.bin", b"kept")

    with pytest.raises(FileNotFoundError):
        keep(folder, "b.bin", tmp_path / "gone")
    with pytest.raises(IsADirectoryError):
        keep(folder, "a.bin", tmp_path)

    assert [(p.name, p.read_bytes()) for p in folder.iterdir()] == [("a.bin", b"kept")]


def test_a_folder_that_cannot_be_made_takes_no_file(tmp_path):
    (tmp_path / "downloads").write_bytes(b"a file where the folder would be")

    with pytest.raises(FileExistsError):
        keep(tmp_path / "downloads", "a.bin", b"x")

    assert (tmp_path / "downloads").read_bytes() == b"a file where the folder would be"


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
