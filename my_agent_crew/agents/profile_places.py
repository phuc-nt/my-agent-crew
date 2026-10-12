"""The places a profile names, followed from the text a file holds them by.

A workspace, a skills folder and a persona are each written as a text, and the text is
followed to a place on the disk as the profile is read. Some texts cannot be: `~somebody`
where nobody is called that, a name longer than the disk gives a file. Following one raised
the library's own error or the disk's, which nobody reads as a bad profile: a start died on
a traceback, an edit was answered 500. A persona's name is not followed until the agents
are listed, so one of those was saved first and failed every listing after. Each is told
here as the bad profile it is, by the key that holds it.
"""

from __future__ import annotations

from pathlib import Path

# How much of a text that cannot be followed the refusal shows.
SHOWN_CHARS = 80


def followed(base: Path, text: str, where: str, key: str) -> Path:
    """Where the text of a workspace or of a skills folder leads from the agent's folder."""
    try:
        return (base / Path(text).expanduser()).resolve()
    except (RuntimeError, OSError, ValueError) as exc:
        raise _refusal(where, key, text, exc) from exc


def persona_names(names: tuple[str, ...], base: Path, where: str) -> tuple[str, ...]:
    """The names as they came, each one the agent's folder can be asked for. Whoever lists
    the agent or puts a turn of it together asks the same of every name."""
    for name in names:
        try:
            (base / name).is_file()
        except (OSError, ValueError) as exc:
            raise _refusal(where, "persona_files", name, exc) from exc
    return names


def _refusal(where: str, key: str, text: str, exc: Exception) -> ValueError:
    shown = text if len(text) <= SHOWN_CHARS else text[:SHOWN_CHARS] + "…"
    # The disk's own words for it where it has some, without the path it repeats.
    reason = getattr(exc, "strerror", None) or str(exc)
    return ValueError(f"{where}: {key} {shown!r} cannot be followed: {reason}")
