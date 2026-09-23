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
NOT_APPLICABLE = "Chưa lưu: đội sẽ không chạy được với thay đổi này — {error}"
APPLY_FAILED = "Đã lưu vào tệp env nhưng chưa áp dụng được ngay: {error}. Khởi động lại máy chủ."
CHECK_OK = "Hoạt động"
CHECK_BOT = "Bot @{username}"
CHECK_MODELS = "{count} mô hình"
CHECK_REACHABLE = "Kết nối được (HTTP {status})"
CHECK_REJECTED = "Bị từ chối (HTTP {status}) — khoá sai hoặc đã thu hồi."
CHECK_HTTP = "Lỗi HTTP {status}"
CHECK_UNREACHABLE = "Không kết nối được: {error}"
