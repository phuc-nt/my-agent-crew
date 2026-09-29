"""Copying a live tree into the run directory, and taking the copy away again.

What stays behind is decided here: the secrets file, the databases, the history, version
control, environments, dependencies and whatever holds a login."""

from __future__ import annotations

import contextlib
import os
import shutil
from collections.abc import Callable
from pathlib import Path

from eval_layout import Mapping

from my_agent_crew.agents.kit import KIT_DIRS

# Left out of the home's top level: the secrets file, the databases, the history and the
# state a running server and its channels keep.
HOME_SKIP = (
    "env",
    "backups",
    "logs",
    "telegram.offset",
    "evals",
    "spill",
    "channels",
    "run-server.zsh",
)
# Left out everywhere: version control, environments, dependencies. Files that look like
# secrets (`.env*`) go too.
ALWAYS_SKIP = (".git", ".venv", "node_modules", "__pycache__")
# Also left out, and counted: what holds a login. A model asked to look inside such a file
# sends it to its provider, and no case needs a session, a private key or a browser profile.
LOGIN_NAMES = (".browser-data", "cookies", "cookies.txt", "trust tokens", "login data")
LOGIN_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".kdbx")
LOGIN_PREFIXES = ("client_secret", "id_rsa", "id_ed25519")


def remove_tree(path: Path) -> None:
    """Delete a copy, read-only directories included; a missing path is fine."""
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if not path.is_dir():
        return
    for dirpath, _dirs, _files in os.walk(path):
        with contextlib.suppress(OSError):
            os.chmod(dirpath, 0o700)
    shutil.rmtree(path)


class _Skipper:
    """The `ignore` callback of `copytree`: what stays behind, and how many links."""

    def __init__(self) -> None:
        self.links = 0
        self.logins = 0

    def __call__(self, root: Path, is_home: bool) -> Callable[[str, list[str]], set[str]]:
        def ignore(directory: str, names: list[str]) -> set[str]:
            here = Path(directory)
            crew_dir = is_home and (here == root or here.parent == root / "agents")
            dropped: set[str] = set()
            for name in names:
                path = here / name
                if path.is_symlink():
                    self.links += 1
                    dropped.add(name)
                elif name in ALWAYS_SKIP or name.startswith(".env"):
                    dropped.add(name)
                elif _holds_a_login(name):
                    self.logins += 1
                    dropped.add(name)
                elif not (path.is_file() or path.is_dir()):
                    dropped.add(name)
                elif name in KIT_DIRS and not crew_dir:
                    dropped.add(name)
                elif is_home and here == root and _left_at_home(name):
                    dropped.add(name)
            return dropped

        return ignore


def _left_at_home(name: str) -> bool:
    return name in HOME_SKIP or name.startswith("agent.sqlite3")


def _holds_a_login(name: str) -> bool:
    lower = name.lower().removesuffix("-journal")
    return (
        lower in LOGIN_NAMES or lower.endswith(LOGIN_SUFFIXES) or lower.startswith(LOGIN_PREFIXES)
    )


def copy_trees(live: Path, home: Path, externals: Mapping, warnings: list[str]) -> _Skipper:
    """Copy the home and each workspace; the skipper says what it left behind."""
    skipper = _Skipper()
    _copy(live, home, skipper(live, True))
    for source, target in externals:
        if source.is_dir():
            _copy(source, target, skipper(source, False))
        else:
            target.mkdir(parents=True)
            warnings.append(f"the workspace {source} does not exist; the copy has an empty one")
    return skipper


def _copy(source: Path, target: Path, ignore: Callable[[str, list[str]], set[str]]) -> None:
    try:
        shutil.copytree(source, target, ignore=ignore)
    except shutil.Error as exc:
        why = "; ".join(f"{src}: {reason}" for src, _dst, reason in exc.args[0][:3])
        raise ValueError(f"could not copy {source}: {why}") from exc


def count_tree(root: Path) -> tuple[int, int]:
    files = size = 0
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            files += 1
            size += os.lstat(os.path.join(dirpath, name)).st_size
    return files, size
