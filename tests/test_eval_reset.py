"""Each run of an eval starts from the server the first run started from: no conversation or
canvas of an earlier run, and the memory files as they were when the eval began."""

from __future__ import annotations

import shutil
from pathlib import Path

import httpx
import pytest
from eval_client import EvalApi
from eval_home import synthetic_home
from eval_reset import RESET_FAILED, MemorySnapshot, ResetError, memory_roots, reset

from tests.http_fake import FakeServer, as_json

ARTIFACTS = "/api/artifacts"
CONVERSATIONS = "/api/conversations"


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def tree(root: Path) -> dict[str, str]:
    """Every path under `root`: a file's text, or `/` for a dir."""
    return {
        p.relative_to(root).as_posix(): "/" if p.is_dir() else p.read_text(encoding="utf-8")
        for p in sorted(root.rglob("*"))
    }


@pytest.fixture
def run(tmp_path: Path) -> Path:
    home = tmp_path / "run" / "home"
    write(home / "memory" / "2027-02-01.md", "one")
    write(home / "memory" / "wiki" / "topics" / "garden.md", "two")
    (home / "memory" / "empty").mkdir()
    write(home / "MEMORY.md", "index")
    write(home / "agent.yaml", "id: default\n")
    return tmp_path / "run"


def snapshot_of(run: Path) -> MemorySnapshot:
    home = run / "home"
    roots = (home / "users" / "owner", home / "memory", home / "MEMORY.md")
    return MemorySnapshot.take(roots, run)


def test_memory_comes_back_as_it_was_whatever_a_run_wrote_changed_or_deleted(run: Path):
    home = run / "home"
    before = tree(run)
    memory = snapshot_of(run)
    write(home / "memory" / "2027-02-01.md", "one, then more")
    (home / "memory" / "wiki" / "topics" / "garden.md").unlink()
    (home / "memory" / "wiki" / "topics").rmdir()
    (home / "memory" / "empty").rmdir()
    write(home / "memory" / "2027-02-02.md", "a note of the run")
    write(home / "memory" / "wiki" / "people" / "an.md", "a page of the run")
    write(home / "MEMORY.md", "index, rewritten")

    memory.restore()

    assert tree(run) == before


def test_a_root_that_was_missing_is_missing_again(run: Path):
    home = run / "home"
    memory = snapshot_of(run)
    write(home / "users" / "owner" / "facts" / "f1.md", "what the run learnt")

    memory.restore()

    assert not (home / "users" / "owner").exists()
    assert (home / "users").is_dir()  # above the root: not the snapshot's to remove


def test_a_file_the_run_turned_into_a_dir_and_back_is_put_back(run: Path):
    home = run / "home"
    before = tree(run)
    memory = snapshot_of(run)
    (home / "MEMORY.md").unlink()
    write(home / "MEMORY.md" / "inside.md", "a dir where the index was")
    (home / "memory" / "empty").rmdir()
    write(home / "memory" / "empty", "a file where a dir was")

    memory.restore()

    assert tree(run) == before


def test_a_link_a_run_left_is_removed_without_following_it(run: Path, tmp_path: Path):
    home = run / "home"
    elsewhere = write(tmp_path / "elsewhere" / "keep.md", "not the eval's")
    memory = snapshot_of(run)
    (home / "memory" / "into-elsewhere").symlink_to(elsewhere.parent, target_is_directory=True)
    (home / "memory" / "2027-02-01.md").unlink()
    (home / "memory" / "2027-02-01.md").symlink_to(elsewhere)

    memory.restore()

    assert not (home / "memory" / "into-elsewhere").exists()
    assert not (home / "memory" / "2027-02-01.md").is_symlink()
    assert (home / "memory" / "2027-02-01.md").read_text(encoding="utf-8") == "one"
    assert elsewhere.read_text(encoding="utf-8") == "not the eval's"


def test_a_memory_root_outside_the_run_dir_is_refused(run: Path, tmp_path: Path):
    with pytest.raises(ValueError, match="outside"):
        MemorySnapshot.take((tmp_path / "live" / "memory",), run)


def test_a_root_that_reaches_outside_through_a_link_is_refused(run: Path, tmp_path: Path):
    live = tmp_path / "live"
    write(live / "memory" / "note.md", "a live note")
    (run / "linked").symlink_to(live, target_is_directory=True)

    with pytest.raises(ValueError, match="outside"):
        MemorySnapshot.take((run / "linked" / "memory",), run)
    assert (live / "memory" / "note.md").exists()


def test_a_link_in_memory_when_the_eval_begins_is_refused(run: Path, tmp_path: Path):
    target = write(tmp_path / "run" / "spare.md", "a file in the run dir")
    (run / "home" / "memory" / "spare.md").symlink_to(target)

    with pytest.raises(ValueError, match="link"):
        snapshot_of(run)


def test_the_memory_roots_are_the_persons_memory_and_each_agents_notes(tmp_path: Path):
    home = synthetic_home(tmp_path / "run").home

    assert memory_roots(home) == (
        home / "users" / "owner",
        home / "memory",
        home / "MEMORY.md",
    )


def api_over(server: FakeServer) -> EvalApi:
    return EvalApi("http://test/api", 5.0, transport=server.transport)


def server_holding(conversations: list[str], canvases: list[str]) -> FakeServer:
    server = FakeServer()
    server.on(CONVERSATIONS, as_json([{"id": c} for c in conversations]), as_json([]))
    server.on(ARTIFACTS, as_json([{"id": a} for a in canvases]), as_json([]))
    for conv in conversations:
        path = f"{CONVERSATIONS}/{conv}"
        server.on(path, as_json({"messages": []}), httpx.Response(204))
    for canvas in canvases:
        server.on(f"{ARTIFACTS}/{canvas}", httpx.Response(204))
    return server


def test_a_reset_deletes_every_canvas_and_conversation_then_puts_memory_back(run: Path):
    memory = snapshot_of(run)
    note = write(run / "home" / "memory" / "2027-02-02.md", "a note of the run")
    server = server_holding(["c1", "k1"], ["a1", "a2"])

    reset(api_over(server), memory)

    assert server.calls() == [
        ("GET", ARTIFACTS),
        ("DELETE", f"{ARTIFACTS}/a1"),
        ("DELETE", f"{ARTIFACTS}/a2"),
        ("GET", CONVERSATIONS),
        ("GET", f"{CONVERSATIONS}/c1"),
        ("DELETE", f"{CONVERSATIONS}/c1"),
        ("GET", f"{CONVERSATIONS}/k1"),
        ("DELETE", f"{CONVERSATIONS}/k1"),
        ("GET", CONVERSATIONS),
        ("GET", ARTIFACTS),
    ]
    assert not note.exists()


def test_a_reset_that_cannot_put_memory_back_fails_and_reaches_nothing_outside(
    run: Path, tmp_path: Path
):
    memory = snapshot_of(run)
    elsewhere = write(tmp_path / "elsewhere" / "keep.md", "not the eval's")
    shutil.rmtree(run / "home" / "memory")
    (run / "home" / "memory").symlink_to(elsewhere.parent, target_is_directory=True)

    with pytest.raises(ResetError, match="could not be put back") as raised:
        reset(api_over(server_holding([], [])), memory)

    assert str(raised.value).startswith(RESET_FAILED)
    assert tree(elsewhere.parent) == {"keep.md": "not the eval's"}


def test_a_reset_that_leaves_anything_on_the_server_fails_and_says_what(run: Path):
    memory = snapshot_of(run)
    server = FakeServer()
    server.on(CONVERSATIONS, as_json([]), as_json([{"id": "c9"}]))
    server.on(ARTIFACTS, as_json([]), as_json([{"id": "a9"}, {"id": "a8"}]))

    with pytest.raises(ResetError) as raised:
        reset(api_over(server), memory)

    assert str(raised.value).startswith(RESET_FAILED)
    assert "conversations c9" in str(raised.value)
    assert "canvases a9, a8" in str(raised.value)
