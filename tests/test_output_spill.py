"""`tools/output_spill.py`: the "spill" that keeps the true original of a tool output next
to the (possibly shaped) copy the model sees in its context, so `tool_output_read` can hand
back the real thing later without re-running whatever produced it.

The file name is a digest of the call id, never the id itself, and the conversation id is
checked against a fixed shape before it becomes part of a path: neither ever comes straight
from the model, but the path is built to be safe even if one somehow did."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from my_agent_crew.tools.output_spill import (
    MAX_SPILL_BYTES,
    Spill,
    copy_conversation,
    remove_conversation,
    sweep,
)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    return tmp_path


def test_write_then_read_returns_the_same_text(home: Path) -> None:
    spill = Spill(home)

    assert spill.write("conv1", "call1", "nội dung gốc") is True
    assert spill.read("conv1", "call1") == "nội dung gốc"


def test_reading_a_call_id_never_written_returns_none(home: Path) -> None:
    spill = Spill(home)

    assert spill.read("conv1", "call-missing") is None


def test_the_file_name_is_a_digest_of_the_call_id_not_the_id_itself(home: Path) -> None:
    spill = Spill(home)
    call_id = "call-with-a-readable-name"

    spill.write("conv1", call_id, "x")

    names = [p.name for p in (home / "spill" / "conv1").iterdir()]
    assert names and call_id not in names[0]


def test_a_call_id_shaped_like_a_path_traversal_never_leaves_the_conversation_folder(
    home: Path,
) -> None:
    """The call id never becomes a path component: it is only ever hashed. Even a
    deliberately hostile id can only ever name a file inside this conversation's folder."""
    spill = Spill(home)
    hostile = "../../../etc/passwd"

    assert spill.write("conv1", hostile, "x") is True

    conv_dir = home / "spill" / "conv1"
    written = list(conv_dir.iterdir())
    assert len(written) == 1
    assert written[0].parent.resolve() == conv_dir.resolve()
    assert spill.read("conv1", hostile) == "x"


@pytest.mark.parametrize("bad_conv_id", ["", "../escape", "a/b", "has spaces", "a" * 65])
def test_a_conversation_id_that_does_not_match_the_fixed_shape_is_refused(
    home: Path, bad_conv_id: str
) -> None:
    spill = Spill(home)

    assert spill.write(bad_conv_id, "call1", "x") is False
    assert spill.read(bad_conv_id, "call1") is None
    assert not (home / "spill").exists() or not list((home / "spill").iterdir())


def test_a_file_over_the_cap_is_truncated_with_a_note(home: Path) -> None:
    spill = Spill(home)
    text = "a" * (MAX_SPILL_BYTES + 1000)

    spill.write("conv1", "call1", text)

    stored = spill.read("conv1", "call1")
    assert stored is not None
    assert len(stored.encode("utf-8")) <= MAX_SPILL_BYTES + 200
    assert "cắt" in stored or "cut" in stored.lower()


def test_sweep_removes_files_older_than_max_age_and_keeps_recent_ones(home: Path) -> None:
    spill = Spill(home)
    spill.write("old-conv", "call1", "cũ")
    spill.write("new-conv", "call2", "mới")
    old_file = next((home / "spill" / "old-conv").iterdir())
    old_stamp = os.stat(old_file).st_mtime - (8 * 86400)
    os.utime(old_file, (old_stamp, old_stamp))

    removed = sweep(home, max_age_days=7)

    assert removed == 1
    assert spill.read("old-conv", "call1") is None
    assert spill.read("new-conv", "call2") == "mới"


def test_sweep_does_not_follow_a_symlink_into_another_directory(home: Path, tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-sweep-target"
    outside.mkdir(exist_ok=True)
    victim = outside / "keep-me.txt"
    victim.write_text("không được đụng")
    spill_root = home / "spill" / "conv1"
    spill_root.mkdir(parents=True)
    link = spill_root / "link.txt"
    link.symlink_to(victim)
    old_stamp = os.stat(link, follow_symlinks=False).st_mtime - (8 * 86400)
    os.utime(link, (old_stamp, old_stamp), follow_symlinks=False)

    sweep(home, max_age_days=7)

    assert victim.read_text() == "không được đụng"


def test_remove_conversation_deletes_the_conversations_own_folder(home: Path) -> None:
    spill = Spill(home)
    spill.write("conv1", "call1", "x")

    remove_conversation(home, "conv1")

    assert not (home / "spill" / "conv1").exists()


def test_remove_conversation_refuses_a_path_that_would_land_outside_spill(home: Path) -> None:
    (home / "spill").mkdir()
    escape_target = home / "not-spill-data"
    escape_target.mkdir()
    marker = escape_target / "marker.txt"
    marker.write_text("must survive")

    remove_conversation(home, "../not-spill-data")

    assert marker.exists()


def test_remove_conversation_on_a_conversation_with_no_spill_directory_does_nothing(
    home: Path,
) -> None:
    remove_conversation(home, "never-had-one")  # must not raise


def test_copy_conversation_duplicates_every_file_with_a_fresh_mtime(home: Path) -> None:
    spill = Spill(home)
    spill.write("source-conv", "call1", "bản gốc")
    src_file = next((home / "spill" / "source-conv").iterdir())
    old_stamp = os.stat(src_file).st_mtime - 100
    os.utime(src_file, (old_stamp, old_stamp))

    copy_conversation(home, "source-conv", "fork-conv")

    assert spill.read("fork-conv", "call1") == "bản gốc"
    dst_file = next((home / "spill" / "fork-conv").iterdir())
    assert os.stat(dst_file).st_mtime > old_stamp


def test_copy_conversation_from_a_source_with_no_spill_directory_does_nothing(home: Path) -> None:
    copy_conversation(home, "never-had-one", "fork-conv")  # must not raise

    assert not (home / "spill" / "fork-conv").exists()
