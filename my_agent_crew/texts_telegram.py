"""Strings for the Telegram channel, split out of `texts` so neither file outgrows its
budget. Import them from `my_agent_crew.texts`, which re-exports this module's names."""

TELEGRAM_CONVERSATION_TITLE = "Telegram · {date}"
TELEGRAM_NEW_CONVERSATION = "Đã mở cuộc trò chuyện mới."
# Fills `{how}` of REPLY_APPROVAL: on Telegram the decision is a slash command.
TELEGRAM_APPROVAL_HOW = "gửi /approve để duyệt, /deny để từ chối"
SHELL_ASK_REASON = "khớp mẫu cần duyệt: `{pattern}`"
TELEGRAM_APPROVAL_EXPIRED = (
    "Yêu cầu duyệt công cụ {name} đã hết hạn chờ, agent tiếp tục như bị từ chối."
)
TELEGRAM_BUSY = "Cuộc trò chuyện đang chờ bạn duyệt một công cụ: /approve hoặc /deny."
TELEGRAM_MEDIA_MISSING = "(không gửi được ảnh: {path})"
# What the agent reads when the person sends photos or a file: one line per saved path,
# the caption (if any) after them, so the model treats the attachments as part of the message.
TELEGRAM_ATTACHMENT_LINE = "[Tệp đính kèm đã lưu: {path}]"
TELEGRAM_ATTACHMENT = "{files}\n{caption}"
TELEGRAM_ATTACHMENT_FAILED = "Không tải được tệp đính kèm từ Telegram ({error}); gửi lại giúp."
TELEGRAM_RUN_UNFINISHED = (
    "Lượt chạy dừng mà chưa có câu trả lời ({reason}); xem chi tiết trên web UI."
)
TELEGRAM_RUN_CUT_SHORT = (
    "Lượt chạy dừng sớm ({reason}), đã chi ${spent:.4f}; "
    "câu trả lời trên có thể chưa đủ. Xem web UI."
)
TELEGRAM_COMMANDS = {
    "new": "Mở cuộc trò chuyện mới.",
    "reset": "Mở cuộc trò chuyện mới (giống /new).",
    "help": "Liệt kê các lệnh.",
    "status": "Trạng thái cuộc trò chuyện hôm nay.",
    "tools": "Các công cụ agent đang có.",
    "approve": "Duyệt công cụ đang chờ.",
    "deny": "Từ chối công cụ đang chờ.",
}
TELEGRAM_HELP_LINE = "/{command} — {description}"
TELEGRAM_UNKNOWN_COMMAND = "Không có lệnh /{command}. Gửi /help để xem các lệnh."
TELEGRAM_STATUS = (
    "{title}\n"
    "Lượt: {turns} · đã chi ${spent:.4f} / ${cap:.2f}\n"
    "Model: {routes}\n"
    "Trạng thái: {state}\n"
    "Lần chạy gần nhất: {run}"
)
TELEGRAM_STATE_IDLE = "sẵn sàng"
TELEGRAM_STATE_OVER_BUDGET = "hết ngân sách"
TELEGRAM_STATE_AWAITING = "đang chờ duyệt {name} (/approve, /deny)"
TELEGRAM_RUN_NONE = "chưa có"
TELEGRAM_RUN = "{status}, {steps} bước, {started}"
TELEGRAM_TOOLS = "Công cụ ({count}):\n{names}"
TELEGRAM_NO_APPROVAL = "Không có công cụ nào đang chờ duyệt."
# The first line of a crew member's brief delivered to the master's chat.
TELEGRAM_AGENT_PREFIX = "[{name}]"
