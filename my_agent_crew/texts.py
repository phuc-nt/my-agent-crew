"""Every string the model or the user reads, in one place. Identifiers stay English;
the language of the text follows the product's default (Vietnamese)."""

DENIED_TOOL = (
    "Người dùng đã TỪ CHỐI hành động này. Không thử lại cùng hành động; nếu cần, hỏi lại "
    "người dùng cách khác."
)
UNKNOWN_TOOL = "Không có công cụ tên {name}."
TOOL_FAILED = "Công cụ lỗi: {error}"
OUTPUT_TRUNCATED = "\n…[đã cắt bớt {dropped} ký tự]"
EMPTY_REPLY = "(không có nội dung)"

WORKSPACE_ESCAPE = "Đường dẫn nằm ngoài thư mục làm việc."
WORKSPACE_NOT_FOUND = "Không có tệp hoặc thư mục: {path}"
WORKSPACE_IS_DIR = "{path} là thư mục, không phải tệp."

URL_SCHEME = "Chỉ hỗ trợ http và https."
URL_PRIVATE = "Từ chối truy cập địa chỉ nội bộ."
URL_REDIRECT = "Trang chuyển hướng tới: {location}"
URL_UNREACHABLE = "Không tới được trang: {error}"
URL_STATUS = "Trang trả về HTTP {status}."

SEARCH_UNREACHABLE = "Không tới được dịch vụ tìm kiếm: {error}"
SEARCH_EMPTY = "Không có kết quả cho: {query}"

MEMORY_SAVED = "Đã ghi nhớ ({count} ghi chú)."
MEMORY_EMPTY = "Không có ghi chú nào khớp."

PREVIOUS_SUMMARY_SECTION_TITLE = "Cuộc trước"
SUMMARY_PROMPT = (
    "Tóm tắt cuộc trò chuyện dưới đây trong tối đa 3 câu tiếng Việt, dưới 600 ký tự. "
    "Giữ lại việc người dùng nhờ làm, kết quả, và điều cần nhớ cho lần sau. "
    "Chỉ trả lời bằng bản tóm tắt, không mở đầu, không gạch đầu dòng.\n\n"
    "--- nội dung ---\n{transcript}"
)
SUMMARY_TRANSCRIPT_LINE = "{role}: {text}"

CONVERSATION_TITLE_DEFAULT = "Cuộc trò chuyện mới"

SKILL_LOCATION = "Thư mục kỹ năng (script, tài liệu kèm theo): {path}"

SHELL_NO_CWD = "Thư mục làm việc không tồn tại: {path}"
SHELL_TIMEOUT = "Lệnh vượt quá {seconds} giây và đã bị dừng."
SHELL_FAILED = "Lệnh thoát với mã {code}.\n{output}"
SHELL_NO_OUTPUT = "(lệnh chạy xong, không có đầu ra)"

JOB_CONVERSATION_TITLE = "[lịch] {name} · {stamp}"
JOB_UNKNOWN = "Không có lịch tên {job_id}."
AGENT_UNKNOWN = "Không có agent tên {agent_id}."
NO_USABLE_ROUTE = "Không có tuyến nào dùng được (thiếu khoá API cho provider): {routes}"
FILE_OUTSIDE_WORKSPACE = "Tệp nằm ngoài thư mục làm việc của agent."

TELEGRAM_CONVERSATION_TITLE = "Telegram · {date}"
TELEGRAM_NEW_CONVERSATION = "Đã mở cuộc trò chuyện mới."
TELEGRAM_HALTED = "Đã dừng ({reason}), đã chi ${spent:.4f}."
TELEGRAM_ERROR = "Lỗi: {message}"
TELEGRAM_APPROVAL = "Agent cần duyệt công cụ {name}: gửi /approve để duyệt, /deny để từ chối."
TELEGRAM_BUSY = "Cuộc trò chuyện đang chờ bạn duyệt một công cụ: /approve hoặc /deny."
TELEGRAM_MEDIA_MISSING = "(không gửi được ảnh: {path})"
TELEGRAM_RUN_UNFINISHED = (
    "Lượt chạy dừng mà chưa có câu trả lời ({reason}); xem chi tiết trên web UI."
)
TELEGRAM_COMMANDS = {
    "new": "Mở cuộc trò chuyện mới.",
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
