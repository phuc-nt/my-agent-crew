"""Cleaning up a private temp directory skips the ask list; everything else still asks.

The exemption decides whether a destructive command runs unattended, so most of these
anchor the cases that must NOT be exempt — a path escaping the temp root, a second
command smuggled in, a shape the parser cannot read.
"""

import tempfile
from pathlib import Path

from my_agent_crew.tools.shell_temp_paths import deletes_only_temp_paths, temp_roots

TMP = tempfile.gettempdir()


def test_deleting_a_sandbox_under_the_temp_root_is_exempt():
    assert deletes_only_temp_paths(f"rm -rf {TMP}/tmp.AbC123")
    assert deletes_only_temp_paths(f"rm -r {TMP}/tmp.AbC123/nested/build")
    assert deletes_only_temp_paths(f"rm -rf {TMP}/a {TMP}/b")
    assert deletes_only_temp_paths(f"rm -rf -- {TMP}/tmp.x")
    assert deletes_only_temp_paths(f"rm -rf '{TMP}/has space'")
    assert deletes_only_temp_paths("rm -rf /tmp/tmp.x")  # a symlinked root on macOS


def test_a_path_that_climbs_out_of_the_temp_root_still_asks():
    """The check resolves `..` before judging, so a traversal cannot buy an exemption."""
    assert not deletes_only_temp_paths(f"rm -rf {TMP}/../../Users/me/code")
    assert not deletes_only_temp_paths("rm -rf /tmp/../etc")
    assert not deletes_only_temp_paths(f"rm -rf {TMP}/ok /Users/me/code")


def test_deleting_a_temp_root_itself_still_asks():
    """Equal to the root is not inside it — that would wipe every sandbox at once."""
    for root in temp_roots():
        assert not deletes_only_temp_paths(f"rm -rf {root}")
    assert not deletes_only_temp_paths("rm -rf /tmp")
    assert not deletes_only_temp_paths("rm -rf /")


def test_a_relative_or_unexpanded_path_still_asks():
    """We cannot resolve these the way the agent's shell would, so we do not try."""
    assert not deletes_only_temp_paths("rm -rf ./scratch")
    assert not deletes_only_temp_paths("rm -rf build")
    assert not deletes_only_temp_paths("rm -rf ~/Downloads")
    assert not deletes_only_temp_paths("rm -rf $TMPDIR/x")
    assert not deletes_only_temp_paths(f"rm -rf {TMP}/$name")


def test_anything_beyond_a_single_rm_still_asks():
    assert not deletes_only_temp_paths(f"rm -rf {TMP}/x && rm -rf /Users/me")
    assert not deletes_only_temp_paths(f"rm -rf {TMP}/x; cat /etc/passwd")
    assert not deletes_only_temp_paths(f"rm -rf $(echo {TMP}/x)")
    assert not deletes_only_temp_paths(f"rm -rf {TMP}/*")
    assert not deletes_only_temp_paths(f"sudo rm -rf {TMP}/x")
    assert not deletes_only_temp_paths(f"rm -rf {TMP}/x > /dev/null")
    assert not deletes_only_temp_paths(f"rm --no-preserve-root -rf {TMP}/x")
    assert not deletes_only_temp_paths(f"rm -rfd {TMP}/x")  # a flag we have not vetted
    assert not deletes_only_temp_paths(f"rm -rf '{TMP}/unbalanced")
    assert not deletes_only_temp_paths("rm -rf")  # no operands
    assert not deletes_only_temp_paths(f"mkfs {TMP}/x")


def test_a_missing_sandbox_is_still_exempt(tmp_path: Path):
    """The directory is usually already gone by cleanup time; that deletes nothing."""
    gone = Path(TMP) / "tmp.does-not-exist-9f3a"
    assert not gone.exists()
    assert deletes_only_temp_paths(f"rm -rf {gone}")


def test_a_symlink_inside_temp_pointing_out_still_asks(tmp_path: Path):
    """Resolution follows the link, so the target decides, not where the link sits."""
    root = Path(TMP).resolve()
    link = root / "tmp.link-probe-7c2b"
    link.unlink(missing_ok=True)
    link.symlink_to(tmp_path)  # tmp_path is pytest's dir, outside the temp root
    try:
        if link.resolve().is_relative_to(root):  # pytest may place it under temp anyway
            return
        assert not deletes_only_temp_paths(f"rm -rf {link}")
    finally:
        link.unlink(missing_ok=True)
