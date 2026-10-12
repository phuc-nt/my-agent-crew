"""What the person is told when the script of a schedule failed.

A script job that ran well and printed nothing says nothing, which is its point. One that
failed opened no turn either, so nothing was sent on, and from the chat the two looked the
same. Here the second is told: one message of the runtime's to the agent's channel, with
which schedule it was, why it ended, and where the run is.

Why is what the run's step kept of what the script said (`activity/step_previews.py`): one
line, whole while it is short and by its head and its tail when it is not, so the sentence a
refusal ends on is there. The script's text and what each of its calls was given are kept on
the same step, and are never read here: the first is the owner's file, the second is
whatever the script handed a tool.

Only the run of the script itself is told. A turn it opened is a conversation's, and is sent
on, failed or not, as a prompt job's is (`runner.py`). A job that runs a command is not told.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from my_agent_crew import texts_script_job as words
from my_agent_crew.activity.step_previews import preview
from my_agent_crew.agents.schedule import SCRIPT
from my_agent_crew.scheduler.jobs import Job
from my_agent_crew.store.runs import FAILED, RunRecord

logger = logging.getLogger(__name__)
# Says a text to an agent's channel, under that agent's name: whether there was one to say
# it to.
Notify = Callable[[str, str], Awaitable[bool]]


def _reason(run: RunRecord) -> str:
    """Why the script ended: what its step kept of what it said, which is the one step of
    such a run. A run that kept nothing of it is told by how it was summed up."""
    said = next((step["output"] for step in reversed(run.steps) if step.get("output")), "")
    return str(said) or run.summary or run.status


def failure_notice(job: Job, run: RunRecord) -> str | None:
    """The message for the run a job came to, or None when there is nothing to tell: the job
    runs no script, its script ended well, or the run is that of a turn."""
    if job.schedule.kind != SCRIPT or run.status != FAILED or run.conversation_id is not None:
        return None
    # A name is the owner's text, of any shape: one line of it opens the message.
    return words.JOB_SCRIPT_FAILED.format(name=preview(job.schedule.name), reason=_reason(run))


async def notify_failure(job: Job, run: RunRecord, notify: Notify | None) -> None:
    """Tells the agent's channel of a script job that failed. With no channel nothing is
    said, and a message that could not be sent is logged and no more: the run is kept as it
    ended either way, and the jobs due after this one still run."""
    text = failure_notice(job, run)
    if notify is None or text is None:
        return
    try:
        sent = await notify(job.agent_id, text)
    except Exception:
        logger.exception("job %s: failure notice not sent", job.id)
    else:
        logger.info("job %s: failure notice sent=%s", job.id, sent)
