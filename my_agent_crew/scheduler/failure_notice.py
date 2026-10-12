"""What the person is told when a job that opened no conversation failed.

A script job that ran well and printed nothing says nothing, which is its point. One that
failed opened no turn either, so nothing was sent on, and from the chat the two looked the
same. A command job and the rewrite of an agent's memory never open a turn at all. Here
the failed ones are told: a message of the runtime's to the agent's channel, with which
schedule it was, why it ended, and where the run is. How often a job that keeps failing is
told is `failure_streaks.py`, which also adds the line each message ends on.

Why is what the one who ran the job hands on (`execute.py`): for a script the line of its
error, or the line that says none of what it stored could be kept (`script_job.py`); for a
command the code it left with and the last line it printed, or that it was stopped at its
limit; for a rewrite of memory what its run was summed up by (`jobs.py`). It is cut as a
failed step is (`activity/step_previews.py`): one line, whole while it is short and by its
head and its tail when it is not, so the sentence a refusal ends on is there. Nothing here
is read off the run. A script's step holds what the script printed before it failed, which
is whatever its tools gave it, and so does its summary where nothing said what ended the
script; the step holds the script's text, which is the owner's file, and what each call was
given. None of those is told. What is told may still repeat them in part, in three ways. A
tool that failed says why in its own words, and may name what it was asked for. An error
the script raised says what the script wrote it to say. And an error the interpreter raised
over a value the script was working on quotes that value (`int()` of a text that is no
number, a key no mapping holds), which may be what a tool gave back. Each is why the script
ended, and is cut as every reason is.

Only a run with no conversation is told. A turn is a conversation's, and is sent on, failed
or not, as a prompt job's is (`runner.py`).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from my_agent_crew import texts_job_failure, texts_script_job
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
    """The message for the run a job came to, or None when there is nothing to tell: the run
    ended some other way than failing, or it is that of a turn. `ended_by` is why it failed.
    Where nobody said, the run is told by its status alone, and never by what it kept of
    what the job said."""
    if run.status != FAILED or run.conversation_id is not None:
        return None
    reason = failure_preview(ended_by) or run.status
    script = job.schedule.kind == SCRIPT
    head = texts_script_job.JOB_SCRIPT_FAILED if script else texts_job_failure.JOB_FAILED
    # A name is the owner's text, of any shape: one line of it opens the message.
    return head.format(name=preview(job.schedule.name), reason=reason)


async def say(job: Job, text: str, notify: Notify | None) -> bool:
    """Says a message about a job to its agent's channel: whether the channel took it. With
    no channel nothing is said, and a message that could not be sent, or was not said in
    time, is logged and no more: the run is kept as it ended either way, and the jobs due
    after this one still run."""
    if notify is None:
        return False
    try:
        async with asyncio.timeout(NOTICE_TIMEOUT_SECONDS):
            sent = await notify(job.agent_id, text)
    except Exception:
        logger.exception("job %s: failure notice not sent", job.id)
        return False
    logger.info("job %s: failure notice sent=%s", job.id, sent)
    return sent is True
