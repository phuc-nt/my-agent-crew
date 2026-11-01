"""What the crew says about how long an approval waits for a person."""

from __future__ import annotations

APPROVAL_TTL_INVALID = (
    "{where}: approval_ttl_seconds phải là số giây nguyên, từ {low} đến {high} (không đặt "
    "trong ngoặc kép), không phải {value!r}."
)

# Where a person settled a request, as the agent and the delegation result word it.
DECIDED_VIA = {"chat": "trên web", "web": "trên web", "telegram": "trên Telegram", "api": "qua API"}
# Added under the output of a call that ran only because a person approved it: without it
# the model reads the result as any other and tells the person nothing asked them.
APPROVED_NOTE = "(Lời gọi này đã dừng chờ duyệt; người dùng đã DUYỆT {via} rồi nó mới chạy.)"
# Added after the refusal of a call a person turned down, so it is not read as a lapse.
DENIED_NOTE = "Người dùng đã bấm từ chối {via}."
# The reason a delegation result gives for a child stopped by a request it was refused.
DELEGATE_DENIED_REASON = "người dùng từ chối duyệt {tool} {via}"
DELEGATE_EXPIRED_REASON = "{tool} hết hạn chờ duyệt, không ai trả lời"
