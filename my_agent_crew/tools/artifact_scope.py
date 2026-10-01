"""What every canvas tool checks before it touches a canvas, and how it words what went
wrong: whether this turn may write at all, whether the canvas is within the agent's reach,
how many versions the turn has written, and what each refusal of the store tells the agent to
do next."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from my_agent_crew.agent.turn_context import canvas_writes, may_write_canvas
from my_agent_crew.artifacts.kinds import (
    LANGUAGE_MAX,
    TITLE_MAX,
    ArtifactTooLarge,
    InvalidLanguage,
    InvalidTitle,
    PayloadMismatch,
    StorageFull,
    UnknownKind,
)
from my_agent_crew.store.artifact_models import (
    VersionConflict,
    VersionGone,
)
from my_agent_crew.texts_canvas import (
    ARTIFACT_BAD_LANGUAGE,
    ARTIFACT_BAD_TITLE,
    ARTIFACT_CHANNEL_CLOSED,
    ARTIFACT_CREATE_BUDGET,
    ARTIFACT_KIND_CLOSED,
    ARTIFACT_NOT_FOUND,
    ARTIFACT_STORAGE_FULL,
    ARTIFACT_TOO_LARGE,
    ARTIFACT_VERSION_CONFLICT,
    ARTIFACT_VERSION_GONE,
    ARTIFACT_WRITE_BUDGET,
)
from my_agent_crew.tools.registry import ToolError

if TYPE_CHECKING:
    from my_agent_crew.store import Store
    from my_agent_crew.store.models import Conversation

# The kinds an agent writes. A person may hold others in the web UI, which an agent reads.
AGENT_KINDS = ("markdown", "code")
# Versions one turn may write to one canvas, and canvases it may create: enough for any
# real piece of work, few enough that a turn stuck in a loop stops long before storage does.
CANVAS_WRITES_PER_TURN = 30
# A canvas being created has no id yet, so creates are counted together under this one.
NEW_CANVAS = ""


def in_scope(
    store: Store,
    artifact_id: str,
    *,
    agent_id: str,
    is_master: bool,
    conversation_id: str,
    root_id: str,
) -> bool:
    """The master reaches every canvas; another agent what `ArtifactStore.reachable` gives
    it. Every input is named, so a caller outside a turn can ask too."""
    return is_master or store.artifacts.is_reachable(
        artifact_id, conversation_id, root_id, agent_id
    )


def not_found(artifact_id: str) -> ToolError:
    return ToolError(ARTIFACT_NOT_FOUND.format(id=artifact_id))


# The canvas tools that write and so pass `check_channel`: the ones a turn on a channel
# with no canvas is told, in its system prompt, not to call.
CANVAS_WRITE_TOOLS = ("artifact_create", "artifact_edit", "artifact_rewrite")


def check_channel(conv: Conversation) -> None:
    if not may_write_canvas(conv):
        raise ToolError(ARTIFACT_CHANNEL_CLOSED)


def check_agent_kind(kind: str) -> None:
    """Agents write only `AGENT_KINDS`, also to a canvas a person made of another kind."""
    if kind not in AGENT_KINDS:
        raise _kind_closed()


def _kind_closed() -> ToolError:
    return ToolError(ARTIFACT_KIND_CLOSED.format(kinds=", ".join(AGENT_KINDS)))


def check_budget(artifact_id: str) -> None:
    """Refuses the write once this turn has written `CANVAS_WRITES_PER_TURN` versions of the
    canvas, or created that many canvases when `artifact_id` is `NEW_CANVAS`. A write that
    changed nothing is not counted: the tool counts with `note_canvas_write` after a write
    that added a version."""
    if canvas_writes(artifact_id) >= CANVAS_WRITES_PER_TURN:
        template = ARTIFACT_CREATE_BUDGET if artifact_id == NEW_CANVAS else ARTIFACT_WRITE_BUDGET
        raise ToolError(template.format(limit=CANVAS_WRITES_PER_TURN))


@contextmanager
def canvas_errors(artifact_id: str = "") -> Iterator[None]:
    """Turns each refusal of the store into what the agent should do about it. A KeyError
    naming the canvas reads as `not_found`, like a canvas out of reach; any other KeyError
    is a bug and passes on, as does a `ToolError` a tool already worded."""
    try:
        yield
    except (UnknownKind, PayloadMismatch):
        raise _kind_closed() from None
    except ArtifactTooLarge as exc:
        message = ARTIFACT_TOO_LARGE.format(kind=exc.kind, size=exc.size, cap=exc.cap)
        raise ToolError(message) from None
    except InvalidTitle:
        raise ToolError(ARTIFACT_BAD_TITLE.format(limit=TITLE_MAX)) from None
    except InvalidLanguage:
        raise ToolError(ARTIFACT_BAD_LANGUAGE.format(limit=LANGUAGE_MAX)) from None
    except StorageFull as exc:
        raise ToolError(ARTIFACT_STORAGE_FULL.format(used=exc.used, cap=exc.cap)) from None
    except VersionGone as exc:
        message = ARTIFACT_VERSION_GONE.format(
            version=exc.version, head=exc.head_version, id=exc.artifact_id
        )
        raise ToolError(message) from None
    except VersionConflict as exc:
        raise ToolError(ARTIFACT_VERSION_CONFLICT.format(head=exc.head_version)) from None
    except KeyError as exc:
        if artifact_id and exc.args == (artifact_id,):
            raise not_found(artifact_id) from None
        raise
