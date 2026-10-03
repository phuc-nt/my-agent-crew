"""The canvas API's refusals: each error the store raises becomes one status code with a body
the web can act on. Caught in the order `canvas_errors` catches them for the agent's tools:
`VersionGone` is a `KeyError` and must be told apart from a missing canvas before the
`KeyError` branch sees it. There is no catch-all for `ValueError`: an author the store refuses
is a bug of the route, and passes on as a 500 like any other error the table does not name."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from fastapi import HTTPException

from my_agent_crew.artifacts.kinds import (
    ArtifactTooLarge,
    InvalidLanguage,
    InvalidTitle,
    NotAnImage,
    PayloadMismatch,
    StorageFull,
    UnknownKind,
)
from my_agent_crew.store.artifact_models import VersionConflict, VersionGone
from my_agent_crew.store.artifacts import ArtifactStore

NOT_FOUND = "artifact not found"
# How many canvases a 507 names, so the person knows what to delete to make room.
LARGEST_SHOWN = 3


@contextmanager
def artifact_errors(store: ArtifactStore, artifact_id: str = "") -> Iterator[None]:
    """A KeyError counts as a missing canvas only when it names `artifact_id`; any other is a
    bug and passes on. A 409 carries the newest version as it is now, read again after the
    conflict: the web merges against that one, and it may be newer than the one the write
    met."""
    try:
        yield
    except VersionGone as exc:
        raise HTTPException(404, {"head_version": exc.head_version}) from None
    except KeyError as exc:
        if artifact_id and exc.args == (artifact_id,):
            raise HTTPException(404, NOT_FOUND) from None
        raise
    except VersionConflict:
        try:
            head = store.head(artifact_id)
        except KeyError:
            raise HTTPException(404, NOT_FOUND) from None
        detail = {"head_version": head.version, "content": head.content, "author": head.author}
        raise HTTPException(409, detail) from None
    except ArtifactTooLarge as exc:
        raise HTTPException(413, {"size": exc.size, "cap": exc.cap}) from None
    except StorageFull as exc:
        detail = {"used": exc.used, "cap": exc.cap, "largest": _largest(store)}
        raise HTTPException(507, detail) from None
    except (UnknownKind, PayloadMismatch, NotAnImage, InvalidTitle, InvalidLanguage) as exc:
        raise HTTPException(422, str(exc)) from None


def _largest(store: ArtifactStore) -> list[dict[str, Any]]:
    """The canvases holding the most bytes across their versions, biggest first. One deleted
    since `sizes()` was read is skipped."""
    shown: list[dict[str, Any]] = []
    for artifact_id, size in sorted(store.sizes().items(), key=lambda item: (-item[1], item[0])):
        try:
            title = store.get(artifact_id).title
        except KeyError:
            continue
        shown.append({"id": artifact_id, "title": title, "size": size})
        if len(shown) == LARGEST_SHOWN:
            break
    return shown
