"""Strings of a stuck turn's move to its agent's escalation route (`agent/escalation.py`).
Import them from `my_agent_crew.texts`, which re-exports every name here."""

# The result of a call the loop guard refused to run when the turn moves to the escalation
# route instead of stopping. The model that reads it is not the one that made the calls.
LOOP_ESCALATED_TOOL = (
    "Không chạy: lệnh này đã được gọi y hệt nhiều lần liên tiếp. Kết quả của các lần trước nằm "
    "ngay phía trên; đừng gọi lại y hệt. Hãy đổi cách làm, hoặc nói rõ điều gì đang chặn."
)
# An edit that names an escalation route the agent could never move to is refused with one of
# these. A file written by hand that does the same still loads, with the route left unused.
ESCALATION_ROUTE_SAME = (
    "Tuyến leo thang {route} trùng với một tuyến chính của agent; hãy chọn một model khác."
)
ESCALATION_ROUTE_UNUSABLE = "Tuyến leo thang {route} không dùng được (thiếu khoá API cho provider)."
