"""What the scheduled jobs reported, in the words the chat was sent them.

A job's report is the answer of the turn it opened: every text the agent wrote in that
turn, in order, as `channels/telegram_outbound.py` sends it. A job whose run opened no
conversation (a command, a memory rewrite, a script that printed nothing) has no answer,
and the chat hears of it only when it failed; neither does a check that said only "OK".
The phone's inbox reads these, so it holds what the chat holds rather than every run.

The turn is the run's, not the conversation's last: the person may answer a report in its
conversation, and the report still reads as it was sent."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass

from my_agent_crew.scheduler.jobs import JOB_SOURCE, NOTHING_TO_REPORT
from my_agent_crew.store import Store
from my_agent_crew.store.message_models import StoredMessage
from my_agent_crew.store.runs import RunRecord

REPORT_LIMIT = 30


@dataclass(frozen=True)
class Report:
    run_id: str
    text: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def turn_text(history: Sequence[StoredMessage], after_seq: int | None) -> str:
    """The texts the agent wrote in the turn that began after `after_seq`: past the message
    that opened it, up to the next one of the person's."""
    parts: list[str] = []
    begun = False
    for stored in history:
        if after_seq is not None and stored.seq <= after_seq:
            continue
        message = stored.message
        if message.role == "user":
            if begun:
                break
            continue
        begun = True
        if message.role == "assistant" and message.content.strip():
            parts.append(message.content.strip())
    return "\n\n".join(parts)


def says_nothing(text: str) -> bool:
    return text.strip().rstrip(".!").strip().upper() in ("", NOTHING_TO_REPORT)


def report_of(store: Store, run: RunRecord) -> Report | None:
    if run.conversation_id is None:
        return None
    text = turn_text(store.history(run.conversation_id), run.after_seq)
    return None if says_nothing(text) else Report(run.id, text)


def job_reports(store: Store, limit: int = REPORT_LIMIT) -> list[Report]:
    """The latest `limit` reports, newest first."""
    reports: list[Report] = []
    for run in store.runs.answered(JOB_SOURCE, limit * 2):
        report = report_of(store, run)
        if report is not None:
            reports.append(report)
        if len(reports) == limit:
            break
    return reports
