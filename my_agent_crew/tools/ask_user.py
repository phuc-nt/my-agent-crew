"""`ask_user`: the agent asking the person something, instead of guessing.

Without this an agent that hits a fork has two bad choices — guess and carry on, or give
up — and a scheduled job has only the first. A nightly ledger check that cannot tell a
paid invoice from an overdue one would rather ask than assert.

The tool is unusual in that it never really runs. It is registered as requiring approval,
which makes the loop stop the turn and record a row; the person answers; the resumed turn
finds the answered row and feeds the answer back as the tool's result. The body below only
runs in the case where nobody answered, and then it says exactly that.

Two rules distinguish it from a tool approval:

* An autonomous conversation still stops. Autonomy means "do not ask me to authorise your
  tools", not "never speak to me". Asking is the model's own decision, and a question that
  auto-approved itself would be answered by nobody and mean nothing.
* Running out of time is not a refusal. A tool nobody authorised must not run, but a
  question nobody answered still has a default, and the agent carries on with it and says
  so in its reply.
"""

from __future__ import annotations

import json
from typing import Any

from my_agent_crew.tools.registry import Tool

ASK_USER_TOOL_NAME = "ask_user"

ASK_USER_DESCRIPTION = (
    "Hỏi người dùng một câu khi bạn thực sự cần họ quyết, thay vì đoán. Dùng khi có nhiều"
    " cách hiểu dẫn tới kết quả khác hẳn nhau, hoặc khi việc sắp làm khó hoàn tác."
    " Đừng hỏi những gì bạn tự tra được bằng công cụ khác."
    " Lượt chạy sẽ dừng lại chờ trả lời; hết thời gian chờ thì bạn nhận lại 'default'"
    " (nếu có) và phải nói rõ trong câu trả lời là bạn đã tự quyết theo mặc định."
)

ASK_USER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": "Câu hỏi, viết gọn và rõ, bằng ngôn ngữ người dùng đang dùng.",
        },
        "options": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Các lựa chọn cho sẵn, nếu câu hỏi là chọn một trong vài phương án."
                " Người dùng vẫn có thể trả lời tự do."
            ),
        },
        "default": {
            "type": "string",
            "description": (
                "Điều bạn sẽ làm nếu không ai trả lời kịp. Luôn đặt giá trị này cho job"
                " chạy nền, vì có thể không có ai ở đó lúc câu hỏi được gửi."
            ),
        },
    },
    "required": ["question"],
}

# What the tool returns when the deadline passed with nobody answering. The agent reads
# this, not an error: it is being told to go on, and told what to say about it.
ASK_USER_UNANSWERED = (
    "Không ai trả lời trong thời gian chờ. Hãy tiếp tục với phương án mặc định"
    ' ("{default}") và nói rõ trong câu trả lời rằng bạn đã tự quyết theo mặc định'
    " vì không nhận được trả lời."
)
ASK_USER_UNANSWERED_NO_DEFAULT = (
    "Không ai trả lời trong thời gian chờ và câu hỏi không có phương án mặc định."
    " Hãy chọn cách hợp lý nhất, làm tiếp, và nói rõ trong câu trả lời rằng bạn đã tự"
    " quyết vì không nhận được trả lời."
)


def unanswered_result(arguments: dict[str, Any]) -> str:
    """What the agent is handed when its question timed out."""
    default = str(arguments.get("default", "") or "")
    if not default:
        return ASK_USER_UNANSWERED_NO_DEFAULT
    return ASK_USER_UNANSWERED.format(default=default)


def answer_result(answer: str) -> str:
    """What the agent is handed once the person has spoken. Their words, unedited: the
    whole point of asking was to get something the agent could not have written itself."""
    return json.dumps({"answered": True, "answer": answer}, ensure_ascii=False)


def options_of(arguments: dict[str, Any]) -> list[str]:
    """The offered choices, defensively: the model writes this field."""
    raw = arguments.get("options")
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


async def _run(arguments: dict[str, Any]) -> str:
    """Only reached when the turn was resumed without an answer — see the module docstring.

    The loop answers a question from its stored row before it would ever call this, so
    reaching here means the row expired."""
    return unanswered_result(arguments)


def build_ask_user_tool() -> Tool:
    return Tool(
        ASK_USER_TOOL_NAME,
        ASK_USER_DESCRIPTION,
        ASK_USER_SCHEMA,
        _run,
        requires_approval=True,
    )
