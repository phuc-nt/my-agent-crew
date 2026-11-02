"""Which of the activity stream's messages are worth waking a phone for, and what it shows.

Four things are: a request waiting on the person (a tool to allow, a question to answer), a
job whose turn answered something, a job that failed, and the answer to a long piece of work the
person started on the web and may have walked away from. What a job says when all is well
("OK") is not, as the chat is not told it either; nor is anything a delegated child or a
Telegram chat ran, since the chat that asked is where its answer goes.

A notice carries only its kind, a fixed sentence and where to open (`texts_push.py`); a
`tag` lets a later notice of the same kind replace an unread one rather than pile up."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from my_agent_crew import texts_push
from my_agent_crew.agent.events import ApprovalRequiredEvent, kind_of
from my_agent_crew.scheduler.jobs import JOB_SOURCE
from my_agent_crew.store.db import Store
from my_agent_crew.store.models import QUESTION
from my_agent_crew.store.runs import ACTIVE_STATUSES, DONE, FAILED

APPROVAL_REQUIRED = kind_of(ApprovalRequiredEvent("", "", "", {}))
INBOX_URL = "/#/inbox"
# A turn shorter than this was most likely watched to its end; a longer one may not be.
LONG_TURN_SECONDS = 60
QUIET_REPLIES = {"OK"}


@dataclass(frozen=True)
class Notice:
    title: str
    body: str
    url: str
    tag: str

    def payload(self) -> dict[str, str]:
        return asdict(self)


def _request(event: dict[str, Any]) -> Notice:
    if event.get("kind") == QUESTION:
        return Notice(texts_push.QUESTION_TITLE, texts_push.QUESTION_BODY, INBOX_URL, "request")
    return Notice(texts_push.APPROVAL_TITLE, texts_push.APPROVAL_BODY, INBOX_URL, "request")


def _seconds(run: dict[str, Any]) -> float:
    try:
        start = datetime.fromisoformat(run["started_at"])
        end = datetime.fromisoformat(run["finished_at"])
    except (KeyError, TypeError, ValueError):
        return 0.0
    return (end - start).total_seconds()


def _quiet(summary: str) -> bool:
    text = summary.strip().rstrip(".!").strip().upper()
    return not text or text in QUIET_REPLIES


def _job(run: dict[str, Any]) -> Notice | None:
    if run.get("status") == FAILED:
        return Notice(texts_push.JOB_FAILED_TITLE, texts_push.JOB_FAILED_BODY, INBOX_URL, "job")
    # A run that opened no conversation has no answer: a command or a rewrite of memory that
    # went well is told nowhere, as the chat is not told it.
    if not run.get("conversation_id"):
        return None
    if run.get("status") == DONE and not _quiet(str(run.get("summary") or "")):
        return Notice(texts_push.JOB_RESULT_TITLE, texts_push.JOB_RESULT_BODY, INBOX_URL, "job")
    return None


def _reply(run: dict[str, Any], store: Store) -> Notice | None:
    conv_id = run.get("conversation_id")
    if run.get("status") != DONE or not conv_id or _seconds(run) < LONG_TURN_SECONDS:
        return None
    try:
        conv = store.get(conv_id)
    except KeyError:
        return None
    if conv.channel or conv.parent_call_id or conv.root_id:
        return None
    return Notice(texts_push.REPLY_TITLE, texts_push.REPLY_BODY, f"/#/chat/{conv_id}", "reply")


def notice_for(payload: dict[str, Any], store: Store) -> Notice | None:
    """The notice one message of the stream calls for, if any."""
    if payload.get("type") == "event":
        event = payload.get("event") or {}
        return _request(event) if event.get("type") == APPROVAL_REQUIRED else None
    if payload.get("type") != "run":
        return None
    run = payload.get("run") or {}
    if run.get("status") in ACTIVE_STATUSES or not run.get("finished_at"):
        return None
    if str(run.get("source", "")).startswith(JOB_SOURCE):
        return _job(run)
    return _reply(run, store)
