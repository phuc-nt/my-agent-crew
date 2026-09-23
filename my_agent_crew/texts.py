"""Every string the model or the user reads, in one place. Identifiers stay English;
the language of the text follows the product's default (Vietnamese)."""

# The delegation and Telegram strings live in their own modules so no one file outgrows
# the line budget, and are pulled in here so every caller keeps writing `texts.<NAME>`
# whichever module a string ended up in.
from my_agent_crew.texts_delegate import *  # noqa: F403
from my_agent_crew.texts_image import *  # noqa: F403
from my_agent_crew.texts_kit import *  # noqa: F403
from my_agent_crew.texts_telegram import *  # noqa: F403

DENIED_TOOL = (
    "Người dùng đã TỪ CHỐI hành động này. Không thử lại cùng hành động; nếu cần, hỏi lại "
    "người dùng cách khác."
)
# Keeps the DENIED_TOOL opening so every reader treating a denial the same way still does.
EXPIRED_TOOL = (
    "Người dùng đã TỪ CHỐI hành động này (hết hạn chờ duyệt, không ai trả lời). "
    "Không thử lại cùng hành động; nếu cần, hỏi lại người dùng cách khác."
)
UNKNOWN_TOOL = "Không có công cụ tên {name}."
TOOL_FAILED = "Công cụ lỗi: {error}"
OUTPUT_TRUNCATED = "\n…[đã cắt bớt {dropped} ký tự]"
# Shaping keeps the JSON parseable, so these markers sit inside string values and array
# slots where a reader looking for the missing part will actually be looking.
OUTPUT_SHAPED_STRING = "…[bớt {dropped} ký tự]…"
OUTPUT_SHAPED_ARRAY = "…[còn {dropped} phần tử nữa]"
OUTPUT_SHAPED_NOTE = (
    "\n[đã rút gọn theo cấu trúc: giữ đủ key, mảng và chuỗi dài bị cắt bớt. "
    "Cần đủ thì đọc thẳng nguồn.]"
)
EMPTY_REPLY = "(không có nội dung)"

WORKSPACE_ESCAPE = (
    "Đường dẫn nằm ngoài thư mục làm việc; tệp ngoài workspace đọc bằng shell_run (cat, sed -n)."
)
WORKSPACE_NOT_FOUND = "Không có tệp hoặc thư mục: {path}"
WORKSPACE_IS_DIR = "{path} là thư mục, không phải tệp."

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

GREP_DESCRIPTION = "Tìm chuỗi (biểu thức chính quy) trong các tệp của thư mục làm việc."
GREP_PARAM_PATTERN = "Biểu thức chính quy."
GREP_PARAM_GLOB = "Lọc theo tên tệp, ví dụ *.py."
GREP_BAD_PATTERN = "Mẫu tìm kiếm sai: {error}"
GREP_NO_MATCH = "Không có dòng nào khớp."
GREP_TIMEOUT = "Tìm kiếm quá lâu, đã dừng. Thu hẹp phạm vi hoặc mẫu tìm."
GLOB_DESCRIPTION = "Tìm tệp theo tên, ví dụ **/*.py, trong thư mục làm việc."
GLOB_PARAM_PATTERN = "Mẫu tên tệp, ví dụ **/*.py."
GLOB_NO_MATCH = "Không có tệp nào khớp."

TOOL_OUTPUT_TRIMMED = "[kết quả cũ đã lược, {chars} ký tự — gọi lại công cụ nếu còn cần]"

URL_SCHEME = "Chỉ hỗ trợ http và https."
URL_PRIVATE = "Từ chối truy cập địa chỉ nội bộ."
URL_REDIRECT = "Trang chuyển hướng tới: {location}"
URL_UNREACHABLE = "Không tới được trang: {error}"
URL_STATUS = "Trang trả về HTTP {status}."

SEARCH_UNREACHABLE = "Không tới được dịch vụ tìm kiếm: {error}"
SEARCH_EMPTY = "Không có kết quả cho: {query}"

MEMORY_SAVED = "Đã ghi nhớ ({count} ghi chú)."
MEMORY_EMPTY = "Không có ghi chú nào khớp."
MEMORY_SEARCH_DESCRIPTION = (
    "Tìm trong ghi nhớ chung về người dùng, MEMORY.md và các ghi chú hằng ngày."
    " Trả về từng mục (gạch đầu dòng hoặc đoạn), không phải từng dòng; gõ không dấu cũng khớp."
)

PREVIOUS_SUMMARY_SECTION_TITLE = "Cuộc trước"
SUMMARY_PROMPT = (
    "Tóm tắt cuộc trò chuyện dưới đây trong tối đa 3 câu tiếng Việt, dưới 600 ký tự. "
    "Giữ lại việc người dùng nhờ làm, kết quả, và điều cần nhớ cho lần sau. "
    "Chỉ trả lời bằng bản tóm tắt, không mở đầu, không gạch đầu dòng.\n\n"
    "--- nội dung ---\n{transcript}"
)
SUMMARY_TRANSCRIPT_LINE = "{role}: {text}"

USER_MEMORY_SAVED = "Đã ghi nhớ về người dùng: {name}."
USER_MEMORY_FORGOTTEN = "Đã xoá ghi nhớ: {name}."
USER_MEMORY_NOT_FOUND = "Không có ghi nhớ nào tên {name}."
USER_MEMORY_PROPOSED = "Đã đề xuất ghi nhớ {name}, chờ người dùng duyệt."
USER_MEMORY_FORGET_PROPOSED = "Đã đề xuất xoá ghi nhớ {name}, chờ người dùng duyệt."
USER_MD_SECTION_TITLE = "USER.md (chung)"
USER_FACTS_SECTION_TITLE = "Ghi nhớ về người dùng"
USER_MEMORY_SAVE_DESCRIPTION = (
    "Ghi nhớ một điều về người dùng, dùng chung cho mọi agent. Mỗi lần gọi là một chủ đề:"
    " tên dạng chu-de-ngan (a-z, 0-9, gạch nối), gọi lại cùng tên để cập nhật."
    " Dùng cho sở thích, hoàn cảnh, cách làm việc — không dùng cho việc chỉ đúng hôm nay."
)
USER_MEMORY_FORGET_DESCRIPTION = (
    "Xoá một điều đã ghi nhớ về người dùng, theo tên của nó trong danh mục ghi nhớ."
)

CONSOLIDATE_PROMPT = (
    "Dưới đây là bộ nhớ dài hạn của một trợ lý và các ghi chép hằng ngày gần đây. "
    "Viết lại bộ nhớ dài hạn sao cho cô đọng hơn: giữ mọi điều còn đúng, gộp các mục "
    "trùng nhau, bổ sung điều đáng nhớ từ ghi chép, bỏ những gì chỉ đúng trong một ngày. "
    "Giữ nguyên tiếng Việt và dạng gạch đầu dòng Markdown, tối đa 24000 ký tự. "
    "Chỉ trả về nội dung bộ nhớ mới, không mở đầu, không giải thích.\n\n"
    "--- bộ nhớ hiện tại ---\n{memory}\n\n--- ghi chép gần đây ---\n{notes}"
)
CONSOLIDATE_JOB_NAME = "Cô đọng bộ nhớ"
CONSOLIDATE_RUN_TITLE = "Cô đọng bộ nhớ · {agent}"
CONSOLIDATE_NOTHING_NEW = "Không có ghi chép nào mới hơn bộ nhớ, bỏ qua."
CONSOLIDATE_UNCHANGED = "Bộ nhớ cô đọng không khác bản hiện tại."
CONSOLIDATE_PROPOSED = "Đã đề xuất bộ nhớ cô đọng, chờ duyệt."
CONSOLIDATE_APPLIED = "Đã ghi bộ nhớ cô đọng."
CONSOLIDATE_EMPTY = "Model không trả về nội dung nào."
CONSOLIDATE_BUSY = "Agent này đang cô đọng bộ nhớ."

CONVERSATION_TITLE_DEFAULT = "Cuộc trò chuyện mới"
TITLE_PROMPT = (
    "Đặt tiêu đề ngắn cho cuộc trò chuyện, dựa trên tin nhắn đầu tiên của người dùng. "
    "3–6 từ, tối đa 60 ký tự, cùng ngôn ngữ với tin nhắn, viết như một câu thường "
    "(chỉ hoa chữ đầu), không dấu chấm cuối, không emoji, không dấu ngoặc kép. "
    "Chỉ trả về tiêu đề.\n\n--- tin nhắn ---\n{message}"
)
# One conversation per agent per day on a channel; `{channel}` is the channel's label.
INBOUND_CONVERSATION_TITLE = "{channel} · {date}"
# What a person reads back from a turn on any platform that shows one message per turn.
REPLY_EMPTY = "Lượt chạy xong nhưng không có nội dung trả lời ({steps} bước). Thử gửi lại câu hỏi."
REPLY_HALTED = "Đã dừng ({reason}), đã chi ${spent:.4f}."
REPLY_ERROR = "Lỗi: {message}"
REPLY_APPROVAL = "Agent cần duyệt công cụ {name}{reason}: {how}."
REPLY_APPROVAL_HOW = "duyệt trên web UI hoặc qua API duyệt"

SKILL_LOCATION = "Thư mục kỹ năng (script, tài liệu kèm theo): {path}"
SKILL_INDEX_HEADING = "## Kỹ năng có sẵn"
SKILL_INDEX_INTRO = (
    "Trước khi làm việc liên quan, gọi `skill_read` với tên kỹ năng để đọc hướng dẫn đầy đủ."
)
SKILL_INDEX_LINE = "- {name}: {description}"
SKILL_INDEX_MISSING_BINS = "[thiếu: {bins}]"
SKILL_INDEX_CLI_HELP = "(tra `{command}` trước khi đoán)"
SKILL_READ_DESCRIPTION = (
    "Đọc hướng dẫn đầy đủ của một kỹ năng trong danh sách 'Kỹ năng có sẵn'. "
    "Gọi trước khi làm việc mà kỹ năng đó mô tả."
)
SKILL_UNKNOWN = "Không có kỹ năng tên {name}. Kỹ năng có sẵn: {names}"
# Sits at the top of the skill body, where the model reads it right before running the
# command, not back in the index it skimmed several steps ago.
SKILL_MISSING_BINS = (
    "CẢNH BÁO: máy này không có lệnh {bins}. Đừng chạy các bước cần lệnh đó; "
    "báo người dùng cài rồi dừng."
)
# The rule that stops a run from burning sixteen steps guessing flags.
CLI_GUESS_RULE = (
    "- Gặp lệnh dòng lệnh chưa chắc cú pháp: chạy `--help` của lệnh đó đúng một lần, và gọi "
    "`skill_read` nếu có kỹ năng liên quan. Không thử quá hai cú pháp mới cho cùng một việc; "
    "sai lần thứ hai thì dừng và báo người dùng."
)
CLI_GUESS_RULE_EN = (
    "- Unsure of a command's syntax: run its `--help` once, and call `skill_read` if a skill "
    "covers it. Never try more than two new syntaxes for the same job; after the second "
    "failure, stop and tell the user."
)

SHELL_NO_CWD = "Thư mục làm việc không tồn tại: {path}"
SHELL_TIMEOUT = "Lệnh vượt quá {seconds} giây và đã bị dừng."
SHELL_FAILED = "Lệnh thoát với mã {code}.\n{output}"
SHELL_NO_OUTPUT = "(lệnh chạy xong, không có đầu ra)"
SHELL_NO_SANDBOX = "Không chạy: agent này bị cắt mạng mà máy không có sandbox-exec."

JOB_CONVERSATION_TITLE = "[lịch] {name} · {stamp}"
JOB_UNKNOWN = "Không có lịch tên {job_id}."
AGENT_UNKNOWN = "Không có agent tên {agent_id}."
RUNTIME_CANNOT_GROW = "Máy chủ này không thêm agent lúc đang chạy được; khởi động lại để nạp."
TEMPLATE_UNKNOWN = "Không có mẫu agent tên {template}."
AGENT_EXISTS = "Agent {agent_id} đã có rồi."
DELEGATE_UNKNOWN_AGENT = "agent {agent_id}: delegates trỏ tới agent không có: {target}"
AGENT_FROM_KIT = "Agent {agent_id} đến từ kit ({path}), sửa thẳng tệp đó."
AGENT_IN_USE_BY = "Còn {agents} đang giao việc cho {agent_id}; bỏ khỏi delegates trước đã."
AGENT_MASTER_UNDELETABLE = "Không xoá được agent chính."
AGENT_ID_INVALID = "Mã agent chỉ gồm chữ thường, số và dấu gạch ngang."
PROFILE_KEY_UNKNOWN = "Không sửa được khoá {keys}."
PERSONA_FILE_UNKNOWN = "Không có tệp tính cách tên {name}. Các tệp: {names}"
PROFILE_KEY_NEEDS_LIST = "Khoá {key} phải là một danh sách."
PATH_OUTSIDE_HOME = "Đường dẫn {path} nằm ngoài thư mục nhà của đội."
MANIFEST_BROKEN = "Tệp agent.yaml hỏng, sửa thẳng tệp rồi thử lại: {error}"
MANIFEST_NOT_A_MAPPING = "Tệp {path} phải là một ánh xạ khoá–giá trị."
# Xếp lịch chỉ dựng một lần lúc khởi động, nên sửa xong vẫn phải
# khởi động lại mới có hiệu lực — nói rõ thay vì để người dùng chờ một việc không chạy.
RESTART_REASON_SCHEDULES = "Lịch chạy mới cần khởi động lại máy chủ."
NO_USABLE_ROUTE = "Không có tuyến nào dùng được (thiếu khoá API cho provider): {routes}"
FILE_OUTSIDE_WORKSPACE = "Tệp nằm ngoài thư mục làm việc của agent."
# Names the provider, because which model went quiet is the one thing that makes
# this actionable — switching route is usually the fix.
BLANK_COMPLETION = "{provider}:{model} trả lời rỗng hai lần liên tiếp. Thử lại hoặc đổi tuyến."
