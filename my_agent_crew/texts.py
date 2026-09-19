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

CONVERSATION_TITLE_DEFAULT = "Cuộc trò chuyện mới"
