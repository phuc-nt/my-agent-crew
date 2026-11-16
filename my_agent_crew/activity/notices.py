"""A host's word to the person: the machine that runs the crew telling them of a problem of
its own (a node gone quiet, a scheduled run missed, a snapshot that failed).

A notice is a run that is over as it starts: the master's, with no conversation, its title
the host's and its summary the whole text. It is listed in the inbox with what the jobs
reported and announced by Web Push with a fixed sentence (`webpush/notices.py`); nothing is
sent to a chat. The summary is stored as given, so the inbox reads all of it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from my_agent_crew import texts_notice
from my_agent_crew.store.runs import DONE, RunRecord

if TYPE_CHECKING:
    from my_agent_crew.activity.hub import ActivityHub

# What a notice's run carries as its source, followed by who told it.
NOTICE_SOURCE = "notice:"
HOST = "host"
TITLE_CHARS = 80
TEXT_CHARS = 2000


def record_notice(hub: ActivityHub, agent_id: str, title: str, text: str) -> RunRecord:
    """Records the notice as a finished run of `agent_id`; an empty title is the default."""
    run = hub.start(agent_id, NOTICE_SOURCE + HOST, title or texts_notice.DEFAULT_TITLE, None)
    hub.finish(run, status=DONE, summary=text)
    return run
