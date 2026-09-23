"""What the credentials routes say back to the person. Never a secret's value: every
message here names the variable, at most."""

from __future__ import annotations

NAME_INVALID = "Tên biến chỉ gồm chữ HOA, số và gạch dưới, bắt đầu bằng chữ (tối đa 64 ký tự)."
NAME_RESERVED = "{name} là biến của hệ thống hoặc của chính máy chủ, không đặt từ đây."
VALUE_EMPTY = "Giá trị đang trống."
VALUE_MULTILINE = "Giá trị không được có xuống dòng hay ký tự điều khiển."
VALUE_TOO_LONG = "Giá trị quá dài (tối đa {limit} ký tự)."
VALUE_NOT_URL = "{name} phải là địa chỉ bắt đầu bằng http:// hoặc https://."
NOT_IN_FILE = "{name} được đặt ngoài tệp env (môi trường lúc khởi động), không xoá được từ đây."
NOT_SET = "{name} chưa được đặt."
NOT_CHECKABLE = "{name} không có phép kiểm tra."
FOREIGN_ORIGIN = "Yêu cầu không đến từ giao diện của máy chủ này."
FOREIGN_HOST = (
    "Máy chủ chỉ trả lời qua localhost hoặc địa chỉ IP, không qua tên {host}. Muốn mở qua tên "
    "này, thêm nó vào {env} trong tệp env rồi khởi động lại — máy chủ không có đăng nhập, nên "
    "ai tới được tên đó đều dùng được cả đội."
)
NOT_APPLICABLE = "Chưa lưu: đội sẽ không chạy được với thay đổi này — {error}"
NOT_REMOVABLE = (
    "Chưa xoá: đội sẽ không chạy được khi thiếu {name} — {error}. Đổi tuyến sang nhà cung cấp "
    "khác trước (thẻ Tuyến mô hình, hoặc mục Mô hình của agent đó), rồi xoá khoá."
)
APPLY_FAILED = "Đã lưu nhưng chưa áp dụng được ngay: {error}. Khởi động lại máy chủ."
CHECK_OK = "Hoạt động"
CHECK_BOT = "Bot @{username}"
CHECK_MODELS = "{count} mô hình"
CHECK_REACHABLE = "Kết nối được (HTTP {status})"
CHECK_REJECTED = "Bị từ chối (HTTP {status}) — khoá sai hoặc đã thu hồi."
CHECK_HTTP = "Lỗi HTTP {status}"
CHECK_USAGE = "Hoạt động — đã dùng {used}/{limit} lượt"
CHECK_RATE_LIMITED = "Khoá nhận, nhưng đang hết lượt hoặc bị giới hạn tốc độ (HTTP 429)."
CHECK_UNREACHABLE = "Không kết nối được: {error}"
ROUTES_EMPTY = "Cần ít nhất một tuyến mô hình."
ROUTES_TOO_MANY = "Tối đa {limit} tuyến."
ROUTE_INVALID = (
    "Tuyến {route} không hợp lệ: nhà cung cấp là chữ thường, số, - hoặc _; tên mô hình không có "
    "dấu cách hay dấu phẩy."
)
ROUTES_FROM_ENV = (
    "Tuyến đang lấy từ biến {env}, biến này thắng config.yaml nên sửa ở đây không có tác dụng. "
    "Bỏ biến đó khỏi tệp env (hoặc môi trường khởi động máy chủ) rồi khởi động lại."
)
ROUTES_NO_PROVIDER = "Chưa lưu: chưa có nhà cung cấp {providers} — đặt khoá API của nó trước."
ROUTES_FAKE = (
    "Chưa lưu: fake chỉ lặp lại tin nhắn, không phải mô hình thật — chọn nhà cung cấp khác."
)
CONFIG_UNWRITABLE = "Chưa lưu: không ghi được config.yaml — {error}"
