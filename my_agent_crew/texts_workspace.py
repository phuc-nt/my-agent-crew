"""Strings for the workspace file tools, split out of `texts` so neither file outgrows
its budget. Import them from `my_agent_crew.texts`, which re-exports every name here."""

WORKSPACE_ESCAPE = (
    "Đường dẫn nằm ngoài thư mục làm việc; tệp ngoài workspace đọc bằng shell_run (cat, sed -n)."
)
WORKSPACE_NOT_FOUND = "Không có tệp hoặc thư mục: {path}"
WORKSPACE_IS_DIR = "{path} là thư mục, không phải tệp."
WORKSPACE_WRITE_OUTSIDE = (
    "Agent này chỉ được ghi tệp dưới: {paths}. {path} không nằm trong đó nên không ghi. Dữ "
    "liệu khác lưu theo cách của workspace (script, bộ nhớ của bạn); đừng tạo tệp chỗ khác."
)

EDIT_DESCRIPTION = (
    "Sửa một tệp bằng cách thay đúng một đoạn văn bản. Đoạn `old` phải khớp chính xác và"
    " duy nhất trong tệp; muốn thay mọi chỗ thì đặt replace_all."
)
EDIT_PARAM_OLD = "Đoạn cần thay, chép nguyên văn từ tệp, đủ dài để chỉ khớp một chỗ."
EDIT_PARAM_NEW = "Đoạn thay thế. Để chuỗi rỗng nghĩa là xoá."
EDIT_EMPTY_OLD = "Đoạn cần thay không được rỗng."
EDIT_NO_MATCH = "Không tìm thấy đoạn cần thay. Đọc lại tệp và chép đúng nguyên văn."
EDIT_AMBIGUOUS = "Đoạn cần thay khớp {count} chỗ. Lấy thêm ngữ cảnh cho duy nhất, hoặc replace_all."
EDIT_DONE = "Đã sửa {path} ({count} chỗ)."
EDIT_DIFF_TRUNCATED = "…[còn {dropped} dòng]"
