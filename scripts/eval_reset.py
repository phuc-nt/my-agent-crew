"""Each run of an eval starts from the server the first run started from.

The runs share one server, and what one run leaves would reach the next: a new conversation
opens with a summary of the one before it in the same channel, `conversation_search` and
`artifact_list` find earlier chats and canvases, and the memory tools that do not ask first
(`memory_save`, the wiki, what the crew knows about the person while they are there) write
files. So before every run `reset` deletes every conversation and canvas on the server and
puts the memory files back as they were when the eval began.

It does not put back what a tool that asks first changes in a case that approves it, the files
a delegated child hands back into a workspace, a schedule an agent made, or a memory proposal
waiting for the person: a case that depends on those starting clean must not cause them."""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from eval_client import EvalApi

from my_agent_crew.agents.kit_agents import load_profiles
from my_agent_crew.config import load_settings

RESET_FAILED = "could not start from a clean server:"


class ResetError(RuntimeError):
    pass


@dataclass(frozen=True)
class MemorySnapshot:
    """The memory files and dirs under `roots` as the eval began; never a path outside
    `inside`, the run dir, so putting them back cannot reach the live tree."""

    inside: Path
    roots: tuple[Path, ...]
    files: Mapping[Path, bytes]
    dirs: frozenset[Path]

    @classmethod
    def take(cls, roots: Iterable[Path], inside: Path) -> MemorySnapshot:
        inside, kept = inside.resolve(), tuple(roots)
        files: dict[Path, bytes] = {}
        dirs: set[Path] = set()
        for root in kept:
            _check_inside(root, inside)
            found, others = _tree(root)
            for path in others:
                if path.is_symlink() or not path.is_file():
                    raise ValueError(f"{path} is a link or not a plain file; the copy has neither")
                files[path] = path.read_bytes()
            dirs.update(found)
        return cls(inside, kept, files, frozenset(dirs))

    def restore(self) -> None:
        """Removes what is new, a link above all, without following it; then makes the dirs
        and writes back the files that are missing or changed."""
        for root in self.roots:
            _check_inside(root, self.inside)
            found, others = _tree(root)
            for path in others:
                if path.is_symlink() or path not in self.files:
                    path.unlink()
            for path in sorted(found, key=lambda p: len(p.parts), reverse=True):
                if path not in self.dirs:
                    path.rmdir()
        for path in sorted(self.dirs, key=lambda p: len(p.parts)):
            path.mkdir(exist_ok=True)
        for path, data in self.files.items():
            if not path.is_file() or path.read_bytes() != data:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)


def memory_roots(home: Path) -> tuple[Path, ...]:
    """Where the memory tools that do not ask first write: what the crew knows about the
    person, and each agent's notes (its wiki among them) and their index."""
    settings = load_settings({"MY_AGENT_HOME": str(home)})
    roots = [settings.user_dir]
    for profile in load_profiles(settings):
        roots += [profile.memory_dir, profile.memory_file]
    return tuple(dict.fromkeys(roots))


def reset(api: EvalApi, memory: MemorySnapshot) -> None:
    """Deletes every canvas, then every conversation, and checks the server holds none of
    either before putting the memory files back. A request that fails raises its httpx error,
    as in a turn; anything left on the server, or memory it cannot put back, `ResetError`."""
    for artifact_id in api.artifact_ids():
        api.delete_artifact(artifact_id)
    for conv_id in api.conversation_ids():
        api.delete_conversation(conv_id)
    conversations, canvases = api.conversation_ids(), api.artifact_ids()
    if conversations or canvases:
        raise ResetError(
            f"{RESET_FAILED} still there after deleting them: conversations"
            f" {', '.join(conversations) or 'none'}; canvases {', '.join(canvases) or 'none'}"
        )
    try:
        memory.restore()
    except (OSError, ValueError) as exc:
        raise ResetError(f"{RESET_FAILED} the memory files could not be put back: {exc}") from exc


def _check_inside(root: Path, inside: Path) -> None:
    if not root.resolve().is_relative_to(inside):
        raise ValueError(f"{root} is outside the run dir {inside}; the eval puts back only its own")


def _tree(root: Path) -> tuple[list[Path], list[Path]]:
    """The dirs under `root`, itself among them, and everything else there: files, links and
    the rest. A root that is not a dir is one of the rest; a missing one has neither."""
    if root.is_symlink() or (root.exists() and not root.is_dir()):
        return [], [root]
    dirs: list[Path] = []
    others: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):  # it lists a link to a dir, never enters
        here = Path(dirpath)
        dirs.append(here)
        links = [name for name in dirnames if (here / name).is_symlink()]
        others += [here / name for name in (*filenames, *links)]
    return dirs, others
