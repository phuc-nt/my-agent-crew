"""Strings for the workspace file tools and the limits on where an agent may write or what
it may run, split out of `texts` so neither file outgrows its budget. Import them from
`my_agent_crew.texts`, which re-exports every name here."""

# Every refusal of an out-of-bounds change ends the same way: a model told only "no"
# looks for another way in (a script, a file elsewhere), and one told to stop and say
# what it needed hands the decision to the person, through whoever gave it the task.
REPORT_BACK = (
    "Việc ngoài phạm vi agent này (sửa code, script, cấu hình, thêm bảng hay tính năng mới) "
    "cần người dùng đồng ý: đừng tìm đường khác để làm, dừng lại và nói rõ cần làm gì, vì "
    'sao. Đang làm việc được giao thì kết thúc bằng "Status: BLOCKED" để agent giao việc '
    "hỏi người dùng."
)

WORKSPACE_ESCAPE = (
    "Đường dẫn nằm ngoài thư mục làm việc; tệp ngoài workspace đọc bằng shell_run (cat, sed -n)."
)
WORKSPACE_NOT_FOUND = "Không có tệp hoặc thư mục: {path}"
WORKSPACE_IS_DIR = "{path} là thư mục, không phải tệp."
WORKSPACE_WRITE_OUTSIDE = (
    "Agent này chỉ được ghi tệp dưới: {paths}. {path} không nằm trong đó nên không ghi. Dữ "
    "liệu khác lưu theo cách của workspace (script, bộ nhớ của bạn). " + REPORT_BACK
)
SHELL_DENIED = 'Không chạy: agent này không được chạy lệnh chứa "{pattern}". ' + REPORT_BACK
SHELL_WRITE_DENIED = (
    "Sandbox đã chặn một lần ghi: lệnh của agent này chỉ ghi được dưới {paths} và thư mục "
    "tạm. " + REPORT_BACK
)
SHELL_WRITES_NOWHERE = "(không thư mục nào của workspace)"

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
