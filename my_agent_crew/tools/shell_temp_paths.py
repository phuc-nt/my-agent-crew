"""Deciding whether a destructive shell command only touches a private temp directory.

The ask list is a coarse substring match, so an agent cleaning up after itself trips it
on every `rm -rf` of a `mktemp -d` sandbox. That stops an unattended run at each cleanup.

This narrows the guard rather than dropping it: a command still asks unless *every* path
it names resolves, symlinks and all, to somewhere strictly inside a system temp root. The
checks are deliberately conservative — anything this module cannot parse with confidence
keeps the approval. Being wrong here deletes the person's files, so an unrecognised shape
is treated as dangerous, never as safe.
"""

from __future__ import annotations

import os
import shlex
import tempfile
from pathlib import Path

# Shell metacharacters mean the command does more than the single cleanup we are exempting
# (a second command, a substitution, a redirect). Any of them and the approval stands.
_SHELL_METACHARACTERS = frozenset(";&|<>`$(){}[]*?!#~\n")
# Flag clusters `rm` accepts for a recursive force delete. `--` ends the options.
_RM_FLAGS = frozenset("rRf")


def temp_roots() -> tuple[Path, ...]:
    """The directories `mktemp -d` may place a sandbox in, fully resolved.

    `/tmp` is a symlink to `/private/tmp` on macOS and `TMPDIR` is usually a per-user
    directory, so both the resolved and unresolved forms are kept: a path is compared
    against what it resolves to, and that has to match a resolved root.
    """
    candidates = [Path(tempfile.gettempdir()), Path("/tmp"), Path("/var/tmp")]
    roots: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:  # a root that does not exist cannot contain anything
            continue
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def _is_inside_a_temp_root(raw: str, roots: tuple[Path, ...]) -> bool:
    """True only when `raw` resolves to a path strictly below one of `roots`.

    Resolution follows symlinks and normalises `..`, so `/tmp/../Users/me/code` is judged
    by where it actually lands. A path equal to a root is not inside it: `rm -rf /tmp`
    wipes every sandbox at once and stays behind the approval.
    """
    if raw.startswith("~") or "$" in raw:  # unexpanded by us, so its target is unknown
        return False
    path = Path(raw)
    if not path.is_absolute():  # resolved against our cwd, not the agent's workspace
        return False
    # `strict=False`: the sandbox may already be gone, and a missing path deletes nothing.
    # Parent symlinks are still followed, which is what keeps the containment check honest.
    resolved = path.resolve()
    return any(resolved != root and resolved.is_relative_to(root) for root in roots)


def _split_rm_arguments(tokens: list[str]) -> list[str] | None:
    """The operands of an `rm` invocation, or None if this is not a plain recursive `rm`."""
    if not tokens or os.path.basename(tokens[0]) != "rm":
        return None
    operands: list[str] = []
    options_ended = False
    for token in tokens[1:]:
        if not options_ended and token == "--":
            options_ended = True
        elif not options_ended and token.startswith("--"):
            return None  # a long option we have not vetted
        elif not options_ended and token.startswith("-") and len(token) > 1:
            if set(token[1:]) - _RM_FLAGS:
                return None  # an unrecognised flag may change what gets deleted
        else:
            operands.append(token)
    return operands


def deletes_only_temp_paths(command: str) -> bool:
    """True when `command` is a single `rm` whose every operand sits in a temp root.

    Anything else — a compound command, a glob, an unparsable quote, no operands at all —
    is False, leaving the ask list to do its job.
    """
    if _SHELL_METACHARACTERS & set(command):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:  # unbalanced quotes: we cannot tell what the operands are
        return False
    operands = _split_rm_arguments(tokens)
    if not operands:  # not an `rm`, or an `rm` with nothing to delete
        return False
    roots = temp_roots()
    if not roots:
        return False
    return all(_is_inside_a_temp_root(operand, roots) for operand in operands)
