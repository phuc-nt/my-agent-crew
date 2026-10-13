"""The one way this program talks to the desktop helper: a line of JSON out over its Unix
socket, a line of JSON back.

Every request opens a connection of its own and closes it, so nothing is left to go stale
when the helper is restarted, and a helper that never answers costs one deadline and no
more. Whatever goes wrong leaves as a `DesktopError` with a code: the helper's own when it
answered, one of three made here when it did not answer in a way that can be read.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# No helper to talk to, none that answered in time, and an answer that cannot be trusted.
ABSENT, TIMEOUT, BAD_ANSWER = "absent", "timeout", "bad_answer"
DEADLINE_SECONDS = 10.0
# A picture of a large display is a few megabytes of base64 on one line: the stream is given
# room for it, and an answer over this is given up rather than held in memory.
MAX_ANSWER_BYTES = 64 * 1024 * 1024
DETAIL_CHARS = 300


class DesktopError(Exception):
    """A request the helper refused, or one it never answered. `code` is what callers act
    on; `detail` is a sentence for a person, the helper's own or one made here."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def _said(exc: BaseException) -> str:
    return (getattr(exc, "strerror", None) or str(exc) or type(exc).__name__)[:DETAIL_CHARS]


@dataclass(frozen=True)
class DesktopClient:
    path: Path
    seconds: float = DEADLINE_SECONDS
    max_bytes: int = MAX_ANSWER_BYTES

    async def request(self, cmd: str, *, seconds: float | None = None, **args: Any) -> dict:
        """Send one command and return the fields of its answer. An argument that is None is
        left out: the helper reads a missing one and a null one alike."""
        request_id = secrets.token_hex(8)
        given = {key: value for key, value in args.items() if value is not None}
        line = json.dumps({"id": request_id, "cmd": cmd, **given}, ensure_ascii=False)
        deadline = self.seconds if seconds is None else seconds
        try:
            async with asyncio.timeout(deadline):
                raw = await self._exchange(line.encode() + b"\n")
        except TimeoutError as exc:
            said = f"no answer to {cmd} within {deadline:g} seconds"
            raise DesktopError(TIMEOUT, said) from exc
        return _answer(raw, request_id)

    async def _exchange(self, line: bytes) -> bytes:
        try:
            reader, writer = await asyncio.open_unix_connection(
                str(self.path), limit=self.max_bytes
            )
        except (OSError, ValueError) as exc:
            # No socket, nobody listening on it, or a path no socket can have.
            raise DesktopError(ABSENT, _said(exc)) from exc
        try:
            writer.write(line)
            await writer.drain()
            return await reader.readline()
        except ValueError as exc:  # the line outgrew the stream's limit
            said = f"the answer is over {self.max_bytes} bytes"
            raise DesktopError(BAD_ANSWER, said) from exc
        except OSError as exc:
            raise DesktopError(BAD_ANSWER, _said(exc)) from exc
        finally:
            writer.close()


def _answer(raw: bytes, request_id: str) -> dict:
    """The fields of a successful answer. A line that is not whole, not an object or not the
    answer to this request is no answer; a refusal leaves as the helper's own code."""
    if not raw.endswith(b"\n"):
        # The helper closes a stranger's connection without a word.
        raise DesktopError(BAD_ANSWER, "the helper closed the connection before it answered")
    try:
        answer = json.loads(raw)
    except (ValueError, RecursionError) as exc:  # not JSON, not UTF-8, or nested too deep
        raise DesktopError(BAD_ANSWER, "the answer is not JSON") from exc
    if not isinstance(answer, dict) or not isinstance(answer.get("ok"), bool):
        raise DesktopError(BAD_ANSWER, "the answer is not an object that says ok")
    refused = answer["ok"] is False
    # A line the helper could not read is refused under an empty id: it never learnt ours.
    if answer.get("id") != request_id and not (refused and answer.get("id") == ""):
        raise DesktopError(BAD_ANSWER, "the answer is to another request")
    if not refused:
        return answer
    code, detail = answer.get("error"), answer.get("detail", "")
    if not isinstance(code, str) or not code or not isinstance(detail, str):
        raise DesktopError(BAD_ANSWER, "the refusal names no error")
    raise DesktopError(code, detail[:DETAIL_CHARS])
