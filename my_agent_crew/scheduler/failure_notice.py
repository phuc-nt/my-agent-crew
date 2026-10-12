"""What the person is told when the script of a schedule failed.

A script job that ran well and printed nothing says nothing, which is its point. One that
failed opened no turn either, so nothing was sent on, and from the chat the two looked the
same. Here the second is told: one message of the runtime's to the agent's channel, with
which schedule it was, why it ended, and where the run is.

Why is what ended the script, as the one who ran it hands it on (`script_job.py`): the line
of its error, or the line that says none of what it stored could be kept. It is cut as a
failed step is (`activity/step_previews.py`): one line, whole while it is short and by its
head and its tail when it is not, so the sentence a refusal ends on is there. Nothing here
is read off the run. Its step holds what the script printed before it failed, which is
whatever its tools gave it, and so does its summary where nothing said what ended the
script; the step holds the script's text, which is the owner's file, and what each call was
given. None of those is told. What is told may still repeat them in part: a tool that
failed says why in its own words, and may name what it was asked for, and an error the
script raised says what the script wrote it to say.

Only the run of the script itself is told. A turn it opened is a conversation's, and is sent
on, failed or not, as a prompt job's is (`runner.py`). A job that runs a command is not told.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from my_agent_crew import texts_script_job as words
from my_agent_crew.activity.step_previews import failure_preview, preview
from my_agent_crew.agents.schedule import SCRIPT
from my_agent_crew.scheduler.jobs import Job
from my_agent_crew.store.runs import FAILED, RunRecord

logger = logging.getLogger(__name__)
# Says a text to an agent's channel, under that agent's name: whether there was one to say
# it to.
Notify = Callable[[str, str], Awaitable[bool]]
# How long the clock waits for the message to be said. It runs the jobs one after another,
# so a chat that never answers would otherwise keep every later job of every agent waiting.
NOTICE_TIMEOUT_SECONDS = 60.0


def failure_notice(job: Job, run: RunRecord, ended_by: str) -> str | None:
    """The message for the run a job came to, or None when there is nothing to tell: the job
    runs no script, its script ended well, or the run is that of a turn. `ended_by` is what
    ended the script. Where nobody said, the run is told by its status alone, and never by
    what it kept of what the script said."""
    if job.schedule.kind != SCRIPT or run.status != FAILED or run.conversation_id is not None:
        return None
    reason = failure_preview(ended_by) or run.status
    # A name is the owner's text, of any shape: one line of it opens the message.
    return words.JOB_SCRIPT_FAILED.format(name=preview(job.schedule.name), reason=reason)


async def notify_failure(job: Job, run: RunRecord, ended_by: str, notify: Notify | None) -> None:
    """Tells the agent's channel of a script job that failed, and what ended its script.
    With no channel nothing is said, and a message that could not be sent, or was not said
    in time, is logged and no more: the run is kept as it ended either way, and the jobs
    due after this one still run."""
    text = failure_notice(job, run, ended_by)
    if notify is None or text is None:
        return
    try:
        async with asyncio.timeout(NOTICE_TIMEOUT_SECONDS):
            sent = await notify(job.agent_id, text)
    except Exception:
        logger.exception("job %s: failure notice not sent", job.id)
    else:
        logger.info("job %s: failure notice sent=%s", job.id, sent)
