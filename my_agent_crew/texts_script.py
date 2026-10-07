"""Strings of `tool_script` (`my_agent_crew/script/`): what the model reads of the tool, and
what it reads when its script is refused, fails or is stopped. Constants only, and nothing
imported: the child process that runs a script loads this module with the site packages
switched off."""

# What the model reads of the tool.
SCRIPT_DESCRIPTION = (
    "Chạy một đoạn script Python ngắn để gọi nhiều công cụ chỉ đọc rồi tự lọc, gộp kết quả; "
    "chỉ những gì script in ra mới quay về cho bạn. Dùng khi phải gọi cùng một công cụ nhiều "
    "lần, hoặc khi kết quả dài mà bạn chỉ cần vài con số hay vài dòng trong đó. Một lời gọi "
    "đơn lẻ thì cứ gọi công cụ trực tiếp.\n"
    "Cách viết: `tools.TEN(tham_so=gia_tri)` hoặc `tools.TEN({{...}})` trả về văn bản kết quả "
    "của công cụ (là JSON thì `json.loads`); công cụ lỗi thì ném lỗi, bắt được bằng "
    "try/except. In ra cái cần bằng `print(...)`; giá trị của biểu thức ở dòng cuối cũng được "
    "in. Mỗi script gọi công cụ tối đa {calls} lần.\n"
    "Chưa rõ tên hay tham số của một công cụ thì tra ngay trong script, không tính vào số lần "
    'gọi: `tools.names()` liệt kê tên mọi công cụ gọi được, `tools.search("từ khoá")` tìm theo '
    'việc (trả list các dict có `name` và `description`), `tools.describe("ten")` cho tham số '
    "đầy đủ.\n"
    "Nhiều lời gọi không phụ thuộc nhau (kết quả cái này không cần cho cái kia) thì gộp một lô "
    "để chạy cùng lúc, nhanh hơn gọi lần lượt: "
    '`tools.batch([{{"tool": "TEN", "args": {{...}}}}, ...])` nhận tối đa {batch} lời gọi, trả '
    "về list kết quả đúng thứ tự đã viết; mỗi phần tử là "
    '`{{"ok": True, "output": văn_bản}}` hoặc `{{"ok": False, "error": lời_lỗi}}`, và một lời '
    "gọi lỗi không làm hỏng các lời gọi còn lại. Mỗi lời gọi trong lô vẫn tính vào {calls} lần. "
    "Ví dụ:\n"
    "{example}\n"
    "Đây là một phần của Python: biến, if/for/while, hàm, list/dict/set/tuple, f-string, "
    "comprehension, try/except, `json`, và len, str, int, float, bool, range, enumerate, zip, "
    "sorted, reversed, min, max, sum, any, all, abs, round, isinstance. Không có import, class, "
    "luỹ thừa `**`, `del`, `with`, đọc thuộc tính (chỉ gọi phương thức của str/list/dict/set), "
    "file hay mạng.{builtins}{mcp}\n"
    "Công cụ phải hỏi trước hoặc có ghi dữ liệu thì không gọi được từ script: gọi trực tiếp."
)
SCRIPT_BUILTINS = "\nCông cụ có sẵn gọi được từ script: {names}."
SCRIPT_MCP = (
    "\nCông cụ MCP gọi được từ script (cần tham số chi tiết thì tra bằng tools.describe):\n{lines}"
)
SCRIPT_MCP_MORE = "- … và {count} công cụ nữa, tìm bằng tools.search."
# Shown to the model inside `SCRIPT_DESCRIPTION`, and run as written by a test: `TEN` stands
# for a tool's name.
SCRIPT_BATCH_EXAMPLE = (
    'answers = tools.batch([{"tool": "TEN", "args": {"id": n}} for n in (1, 2, 3)])\n'
    "for answer in answers:\n"
    '    print(answer["output"] if answer["ok"] else answer["error"])'
)
SCRIPT_SOURCE = "Mã script Python. Kết quả là những gì script in ra bằng print."

# The tool's own answers.
SCRIPT_NO_SOURCE = "Thiếu `script`: mã Python cần chạy."
SCRIPT_TOO_LONG = "Script dài quá {most} ký tự. Viết gọn lại."
SCRIPT_NO_OUTPUT = "(script chạy xong, không in ra gì: dùng print để lấy kết quả)"
SCRIPT_TIMED_OUT = "Script bị dừng: quá {seconds:g} giây mà chưa xong."
SCRIPT_OUT_OF_CPU = "Script bị dừng: tính toán quá lâu. Chia nhỏ việc hoặc xử lý ít dữ liệu hơn."
SCRIPT_DIED = "Script bị dừng giữa chừng mà không trả kết quả."
# Opens the answer of a script that did not run to its end, whatever ended it; what it had
# printed and why it ended follow. A stored answer keeps no word of whether the call failed,
# and a script prints what it likes, so the web knows such an answer by this line alone
# (`web/src/lib/tool-reply.ts`).
SCRIPT_FAILED = "Script không chạy xong."

# A name that is no tool of the agent's. The script may catch it and look for the right one.
SCRIPT_UNKNOWN_TOOL = (
    "Không có công cụ `{name}`.{near} `tools.names()` liệt kê mọi công cụ gọi được; "
    '`tools.search("từ khoá")` tìm theo việc.'
)
SCRIPT_DID_YOU_MEAN = " Ý bạn là `{near}`?"
# Added to the answer of a call that failed on the wrong parameters: what to call it with.
SCRIPT_CALL_LIKE = "Cách gọi: {line}"

# What a script asks to know of the tools it may call: `tools.names`, `search`, `describe`.
SCRIPT_LOOKUP_USAGE = "`{shape}`: tham số sai."
SCRIPT_TOO_MANY_LOOKUPS = "đã tra công cụ quá {most} lần: dùng lại kết quả đã có."
SCRIPT_NO_LOOKUPS = "không tra được công cụ ở đây."
SCRIPT_DESCRIBE_PARAMS = "Tham số:"
SCRIPT_DESCRIBE_NONE = "Không có tham số."
SCRIPT_DESCRIBE_REQUIRED = ", bắt buộc"
SCRIPT_DESCRIBE_CUT = "… (còn nữa, đã cắt bớt)"

# `tools.batch`: several calls made at once. A batch asked for the wrong way is a mistake the
# script may catch, and none of its calls is made or counted. The first two are never formatted.
SCRIPT_BATCH_USAGE = (
    'tools.batch nhận một list các lời gọi: tools.batch([{"tool": "TEN", "args": {...}}, ...]).'
)
SCRIPT_BATCH_EMPTY = "lô rỗng: tools.batch cần ít nhất một lời gọi."
SCRIPT_BATCH_TOO_MANY = "lô dài quá {most} lời gọi: chia thành nhiều lô."
SCRIPT_BATCH_ITEM = (
    'phần tử {index} của lô (đếm từ 0) phải là {{"tool": "TEN", "args": {{...}}}}: '
    "`tool` là chuỗi, `args` là dict hoặc bỏ trống, không có khoá nào khác."
)
SCRIPT_BATCH_AT = "lời gọi {index} trong lô: {error}"
SCRIPT_BATCH_ROOM = (
    "lô có {count} lời gọi mà script chỉ còn gọi được {left} trong {most} lần: "
    "bỏ bớt hoặc chia nhỏ lô."
)
SCRIPT_NO_BATCHES = "không gọi theo lô được ở đây."
# The answer of a call that was not made because another call of its batch is one the script
# may not make: the script ends there, so it is never read, but each call has one.
SCRIPT_BATCH_NOT_RUN = "không chạy: lô này có lời gọi mà script không được gọi."

# A call a script may not make although the tool exists. None of these can be caught: the
# script ends there.
SCRIPT_NOT_FROM_SCRIPT = "`{name}` không gọi được từ script: {instead}."
SCRIPT_ASKS_FIRST = (
    "`{name}` phải hỏi trước hoặc có ghi dữ liệu nên không gọi được từ script: {instead}."
)
# What to do instead, for a tool told up front and for one that waits to be found.
SCRIPT_CALL_DIRECTLY = "gọi trực tiếp"
SCRIPT_LOAD_THEN_CALL = "nạp bằng tool_search rồi gọi trực tiếp"
SCRIPT_TOO_MANY_CALLS = "Script đã gọi công cụ quá {most} lần. Gộp việc lại hoặc chia nhiều script."

# How a run ends when it does not end well.
SCRIPT_SYNTAX = "Lỗi cú pháp ở dòng {line}: {error}"
SCRIPT_REFUSED = "Dòng {line}: {why}"
SCRIPT_UNSUPPORTED = "`{what}` không dùng được trong script."
SCRIPT_NO_ATTRIBUTE = (
    "`.{name}` không đọc được: script chỉ gọi phương thức (`x.{name}(...)`), không đọc thuộc tính."
)
SCRIPT_ERROR = "Lỗi ở dòng {line}: {error}"
SCRIPT_HALTED = "Dừng ở dòng {line}: {reason}"

# Limits.
SCRIPT_OUT_OF_STEPS = "script chạy quá {most} bước. Xử lý ít dữ liệu hơn hoặc bỏ vòng lặp thừa."
SCRIPT_OUT_OF_ROOM = "script tạo ra quá nhiều dữ liệu. Lọc bớt trước khi gom lại."
SCRIPT_TOO_MUCH_OUTPUT = "script in ra quá {most} ký tự. Chỉ in phần cần, đã gộp hoặc lọc."
SCRIPT_TOO_DEEP = "hàm gọi lồng nhau quá sâu."
SCRIPT_TOO_NESTED = "dữ liệu lồng nhau quá sâu hoặc quá nhiều phần tử để viết ra."
SCRIPT_BIG_NUMBER = "số nguyên quá lớn."
SCRIPT_RANGE = "range dài quá {most} phần tử."
SCRIPT_ARGS_TOO_BIG = "tham số gọi công cụ dài quá {most} ký tự."

# Mistakes a script can catch and carry on from.
SCRIPT_NO_NAME = "chưa có tên `{name}`."
SCRIPT_NAMESPACE = "`{name}` chỉ dùng để gọi: `{name}.TEN(...)`."
SCRIPT_NO_METHOD = "{kind} không có phương thức `{name}` trong script."
SCRIPT_NO_JSON = "json chỉ có `loads` và `dumps`."
SCRIPT_NOT_CALLABLE = "{kind} không phải hàm, không gọi được."
SCRIPT_BAD_CALL = "gọi hàm `{name}` sai tham số."
SCRIPT_NO_KEYWORDS = "hàm `{name}` không nhận tham số theo tên."
SCRIPT_SPREAD = "`**` chỉ mở được một dict (khi gọi hàm thì khoá phải là chuỗi)."
SCRIPT_NOT_INDEXED = "{kind} không lấy phần tử bằng [] được."
SCRIPT_NOT_ITERABLE = "{kind} không duyệt được."
SCRIPT_BAD_TARGET = "chỉ gán được vào tên, vào `list[i]` hoặc `dict[k]`."
SCRIPT_UNPACK = "tách {got} giá trị vào {want} tên."
SCRIPT_NO_PERCENT = "không định dạng chuỗi bằng `%`: dùng f-string."
SCRIPT_BAD_FORMAT = "định dạng `{spec}` trong f-string không được hỗ trợ."
SCRIPT_ISINSTANCE = "isinstance chỉ nhận str, int, float, bool, list, dict, set, tuple."
SCRIPT_SUM = "sum chỉ cộng số."
SCRIPT_EMPTY = "{name}() của một dãy rỗng."
SCRIPT_NOTHING_TO_RAISE = "`raise` trống chỉ dùng trong except."
SCRIPT_TOOL_ARGS = "gọi công cụ bằng tham số theo tên, hoặc đúng một dict."
SCRIPT_TOOL_ARGS_JSON = "tham số gọi công cụ phải là dữ liệu JSON (chuỗi, số, list, dict)."
