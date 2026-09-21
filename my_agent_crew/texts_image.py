"""Strings of the image-reading tool. Re-exported through `texts`."""

IMAGE_READ_DESCRIPTION = (
    "Xem một ảnh (jpg, png, webp, gif) bằng model nhìn ảnh và trả lời câu hỏi về nó."
    " Đường dẫn tương đối trong thư mục làm việc, hoặc tuyệt đối với tệp đính kèm trong"
    " inbox (`[Tệp đính kèm đã lưu: …]`). Không có câu hỏi thì mô tả ảnh và chép mọi"
    " chữ, số đọc được. Mỗi lần gọi tốn một lượt model; hỏi gộp thay vì gọi nhiều lần."
)
IMAGE_PARAM_PATH = "Đường dẫn tệp ảnh."
IMAGE_PARAM_QUESTION = "Câu hỏi hoặc điều cần trích từ ảnh; bỏ trống để mô tả chung."
IMAGE_DEFAULT_QUESTION = "Mô tả ảnh này và chép lại nguyên văn mọi chữ, số, bảng đọc được."
IMAGE_SYSTEM = (
    "Bạn là bộ đọc ảnh cho một trợ lý. Trả lời bằng tiếng Việt, ngắn gọn, đúng sự thật;"
    " chép nguyên văn chữ và số thấy trong ảnh; nói rõ khi không chắc hoặc không thấy."
)
IMAGE_OUTSIDE = "Ảnh phải nằm trong thư mục làm việc hoặc thư mục home của my-agent-crew."
IMAGE_NOT_FOUND = "Không có tệp ảnh: {path}"
IMAGE_UNSUPPORTED = "Không hỗ trợ định dạng {suffix}; chỉ nhận {kinds}."
IMAGE_TOO_LARGE = "Ảnh {size:.1f} MB vượt mức {limit:.0f} MB."
IMAGE_READ_FAILED = "Không đọc được ảnh: {error}"
IMAGE_EMPTY = "(model không nói gì về ảnh này)"
