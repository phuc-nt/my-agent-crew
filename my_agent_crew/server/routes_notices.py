"""`POST /api/notices`: the host that runs the crew tells the person something.

The notice is listed in the inbox and pushed with a fixed sentence (`activity/notices.py`).
A host reaches this server as the person's own page does; the text is told as given, never
read by an agent."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, StringConstraints

from my_agent_crew.activity.notices import TEXT_CHARS, TITLE_CHARS, record_notice
from my_agent_crew.server.deps import Rt

router = APIRouter(tags=["notices"])


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TEXT_CHARS)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, max_length=TITLE_CHARS)]


class NoticeBody(BaseModel):
    text: Text
    # Empty is the default title (`texts_notice.DEFAULT_TITLE`).
    title: Title = ""


@router.post("/notices", status_code=201)
def post_notice(body: NoticeBody, rt: Rt) -> dict[str, str]:
    run = record_notice(rt.hub, rt.default.agent.id, body.title, body.text)
    return {"run_id": run.id}
