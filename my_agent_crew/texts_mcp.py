"""Strings of the MCP client (`my_agent_crew/mcp/`): what the model reads when a call to a
server fails, and what the owner reads on the Connections screen. Imported from here
rather than through `texts`, which is at its line budget."""

# One call to a server, as the model or the owner reads its failure.
MCP_TIMEOUT = "Máy chủ MCP {server} không trả lời trong {seconds:g} giây."
MCP_UNREACHABLE = "Không kết nối được máy chủ MCP {server}: {error}"
MCP_BAD_HEADER = (
    "Không gửi được yêu cầu tới máy chủ MCP {server}: một header có giá trị không viết được "
    "lên đường truyền. Kiểm tra khoá trong biến môi trường, nhất là dấu xuống dòng ở giữa."
)
MCP_HTTP_STATUS = "Máy chủ MCP {server} trả về HTTP {status}{detail}."
MCP_REDIRECT = "Máy chủ MCP {server} chuyển hướng sang địa chỉ khác; không đi theo."
MCP_TOO_LARGE = "Máy chủ MCP {server} trả về quá nhiều dữ liệu (hơn {megabytes} MB)."
MCP_NO_ANSWER = "Máy chủ MCP {server} đóng kết nối mà không trả lời."
MCP_BAD_ANSWER = "Máy chủ MCP {server} trả lời không đúng giao thức."
MCP_TOO_MANY_TOOLS = (
    "Máy chủ MCP {server} liệt kê hơn {limit} công cụ nên không công cụ nào của nó được nhận."
)
MCP_VERSION = "Máy chủ MCP {server} dùng phiên bản giao thức {version!r} chưa được hỗ trợ."
MCP_SESSION_GONE = "Máy chủ MCP {server} đã bỏ phiên làm việc."
MCP_RPC_ERROR = "Máy chủ MCP {server} báo lỗi: {message}"
MCP_UNAUTHORIZED = "Máy chủ MCP {server} từ chối: chưa đăng nhập hoặc phiên đăng nhập đã hết."
# A tool's result that carried no text, and one the server marked as failed without saying why.
MCP_EMPTY_RESULT = "(công cụ chạy xong, không trả về nội dung)"
MCP_TOOL_FAILED = "Công cụ báo lỗi mà không nói lý do."
MCP_BLOCK = "[{kind}: {detail}]"
MCP_DESCRIPTION = "[MCP {server}] {description}"

# `tool_search`: what the model reads of it, and what it answers.
TOOL_SEARCH_DESCRIPTION = (
    "Tìm và nạp công cụ của các máy chủ MCP được giao cho bạn: {servers}. Các công cụ này "
    "không khai sẵn: phải tìm ở đây trước, rồi mới gọi được với đúng tham số. Hãy tìm trước "
    "khi kết luận rằng bạn không làm được một việc thuộc các máy chủ đó. Dùng vài từ khoá "
    "tiếng Anh ngắn gọn nói việc cần làm (ví dụ: search pages, create database), hoặc ghi "
    "đúng tên công cụ nếu đã biết."
)
TOOL_SEARCH_QUERY = "Vài từ khoá tiếng Anh nói việc cần làm, hoặc tên công cụ."
TOOL_SEARCH_LIMIT = "Số công cụ nạp tối đa (mặc định {default}, nhiều nhất {most})."
TOOL_SEARCH_SERVER = "{name} ({description})"
TOOL_SEARCH_COUNT = "{name} ({count} công cụ)"
TOOL_SEARCH_NO_QUERY = "Thiếu `query`: vài từ khoá nói việc cần làm."
TOOL_SEARCH_LOADED = "Đã nạp {count} công cụ, gọi trực tiếp bằng tên:"
TOOL_SEARCH_MORE = (
    "Còn {count} công cụ khác khớp; tìm lại với từ khoá hẹp hơn nếu chưa thấy cái cần."
)
TOOL_SEARCH_NONE = (
    "Không có công cụ nào khớp, chưa nạp gì. Đang có: {servers}. Thử từ khoá tiếng Anh khác."
)

# Why a server is not connected, as the Connections screen shows it.
MCP_MISSING_ENV = "Thiếu biến môi trường: {names}."
MCP_KEY_REFUSED = "Máy chủ từ chối khoá trong header Authorization."
MCP_NO_CLIENT = "Chưa có kết nối mạng để gọi máy chủ."
MCP_UNKNOWN_SERVER = "Không có máy chủ MCP tên {name}."
MCP_AGENT_UNKNOWN_SERVER = "Không có máy chủ MCP tên {name} trong config.yaml."

# Signing in with OAuth.
MCP_LOGIN_LOCAL_ONLY = (
    "Chỉ đăng nhập được khi mở trang này trên chính máy đang chạy crew "
    "(địa chỉ localhost hoặc 127.0.0.1)."
)
MCP_LOGIN_HEADER_KEY = "Máy chủ này dùng khoá trong header, không đăng nhập bằng OAuth."
MCP_LOGIN_NOT_ASKED = "Máy chủ này không yêu cầu đăng nhập."
MCP_OAUTH_URL = "Địa chỉ đăng nhập {url} bị từ chối: phải là https và không trỏ vào mạng nội bộ."
MCP_OAUTH_DISCOVERY = "Không đọc được thông tin đăng nhập của máy chủ: {error}"
MCP_OAUTH_SLOW = "quá {seconds:g} giây vẫn chưa trả lời xong"
MCP_OAUTH_ISSUER = "Máy chủ đăng nhập tự nhận là {got}, không khớp với {expected}."
MCP_OAUTH_NO_ISS = (
    "Máy chủ đăng nhập hứa tự xưng tên khi trả mã nhưng đã không làm; từ chối mã này."
)
MCP_OAUTH_MOVED = (
    "Máy chủ giờ chỉ sang nơi đăng nhập {got}, khác nơi đã cấp phiên đang giữ ({expected}). "
    "Phiên cũ đã bỏ; nếu máy chủ thật sự đổi nơi đăng nhập thì bấm đăng nhập lại."
)
MCP_OAUTH_NO_PKCE = "Máy chủ đăng nhập không hỗ trợ PKCE S256; từ chối đăng nhập."
MCP_OAUTH_RESOURCE = "Máy chủ khai tài nguyên {resource} không cùng nguồn với địa chỉ đã cấu hình."
MCP_OAUTH_NO_REGISTRATION = (
    "Máy chủ đăng nhập không cho tự đăng ký ứng dụng. Đặt {name} bằng client id bạn đã đăng ký."
)
MCP_OAUTH_REGISTER = "Đăng ký ứng dụng với máy chủ đăng nhập thất bại: {error}"
MCP_OAUTH_TOKEN = "Đổi mã lấy token thất bại: {error}"
MCP_OAUTH_TOKEN_TYPE = "Máy chủ đăng nhập trả loại token {kind!r}, chỉ hỗ trợ Bearer."
MCP_OAUTH_LATE = "Lần đăng nhập này đã quá hạn. Bấm đăng nhập lại."
MCP_OAUTH_DENIED = "Đăng nhập bị từ chối: {error}"
MCP_OAUTH_NO_CODE = "Máy chủ đăng nhập không trả mã xác nhận."
MCP_OAUTH_STORE = "Không lưu được token: {error}"
