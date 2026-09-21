"""Strings for the Telegram channel, split out of `texts` so neither file outgrows its
budget. Import them from `my_agent_crew.texts`, which re-exports this module's names."""

TELEGRAM_CONVERSATION_TITLE = "Telegram · {date}"
TELEGRAM_NEW_CONVERSATION = "Đã mở cuộc trò chuyện mới."
TELEGRAM_NEW_CONVERSATION_ALL = "Đã mở cuộc trò chuyện mới cho tất cả agent: {agents}."
TELEGRAM_NEW_CONVERSATION_ONE = (
    "Đã mở cuộc trò chuyện mới với {name}. Các agent khác giữ nguyên cuộc của họ."
)
# Fills `{how}` of REPLY_APPROVAL: on Telegram the decision is a slash command.
TELEGRAM_APPROVAL_HOW = "gửi /approve để duyệt, /deny để từ chối"
SHELL_ASK_REASON = "khớp mẫu cần duyệt: `{pattern}`"
TELEGRAM_APPROVAL_EXPIRED = (
    "Yêu cầu duyệt công cụ {name} đã hết hạn chờ, agent tiếp tục như bị từ chối."
)
TELEGRAM_BUSY = "Cuộc trò chuyện đang chờ bạn duyệt một công cụ: /approve hoặc /deny."
TELEGRAM_MEDIA_MISSING = "(không gửi được ảnh: {path})"
# What the agent reads when the person sends a photo or a file: the saved path first, the
# caption (if any) after it, so the model treats the attachment as part of the message.
TELEGRAM_ATTACHMENT = "[Tệp đính kèm đã lưu: {path}]\n{caption}"
TELEGRAM_ATTACHMENT_FAILED = "Không tải được tệp đính kèm từ Telegram ({error}); gửi lại giúp."
TELEGRAM_RUN_UNFINISHED = (
    "Lượt chạy dừng mà chưa có câu trả lời ({reason}); xem chi tiết trên web UI."
)
TELEGRAM_RUN_CUT_SHORT = (
    "Lượt chạy dừng sớm ({reason}), đã chi ${spent:.4f}; "
    "câu trả lời trên có thể chưa đủ. Xem web UI."
)
TELEGRAM_COMMANDS = {
    "new": "Mở cuộc trò chuyện mới cho mọi agent (@id trước /new để chỉ cắt một agent).",
    "reset": "Mở cuộc trò chuyện mới (giống /new).",
    "help": "Liệt kê các lệnh.",
    "status": "Trạng thái cuộc trò chuyện hôm nay.",
    "tools": "Các công cụ agent đang có.",
    "agents": "Các agent trên bot này; gửi @id để chuyển.",
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
TELEGRAM_AGENT_PREFIX = "[{name}]"
TELEGRAM_AGENTS = (
    "Các agent trên bot này (gửi @id để chuyển, ▶ là agent đang nói chuyện):\n{agents}"
)
TELEGRAM_AGENT_LINE = "{mark} @{agent_id} — {name}"
TELEGRAM_AGENT_CURRENT = "▶"
TELEGRAM_AGENT_OTHER = "•"
TELEGRAM_AGENT_SWITCHED = "Đang nói chuyện với {name} (@{agent_id})."
TELEGRAM_AGENT_UNKNOWN = "Không có agent @{agent_id}.\n{agents}"
