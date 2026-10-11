"""Strings of `tool_script` (`my_agent_crew/script/`): what the model reads of the tool, and
what it reads when its script is refused, fails or is stopped. Constants only, and nothing
imported: the child process that runs a script loads this module with the site packages
switched off."""

# What the model reads of the tool: how a script is written, whatever it may call.
_SCRIPT_HOW = (
    "chỉ những gì script in ra mới quay về cho bạn. Dùng khi phải gọi cùng một công cụ nhiều "
    "lần, hoặc khi kết quả dài mà bạn chỉ cần vài con số hay vài dòng trong đó. Một lời gọi "
    "đơn lẻ thì cứ gọi công cụ trực tiếp.\n"
    "Cách viết: `tools.TEN(tham_so=gia_tri)` hoặc `tools.TEN({{...}})` trả về văn bản kết quả "
    "của công cụ (là JSON thì `json.loads`); công cụ lỗi thì ném lỗi, bắt được bằng "
    "try/except. In ra cái cần bằng `print(...)`; giá trị của biểu thức ở dòng cuối cũng được "
    "in. Mỗi script được tối đa {calls} lời gọi.\n"
    "Chưa rõ tên hay tham số của một công cụ thì tra ngay trong script, không tính vào số lần "
    'gọi: `tools.names()` liệt kê tên mọi công cụ gọi được, `tools.search("từ khoá")` tìm theo '
    'việc (trả list các dict có `name` và `description`), `tools.describe("ten")` cho tham số '
    "đầy đủ.\n"
    "Nhiều lời gọi không phụ thuộc nhau (kết quả cái này không cần cho cái kia) thì gộp một lô "
    "để chạy cùng lúc, nhanh hơn gọi lần lượt: "
    '`tools.batch([{{"tool": "TEN", "args": {{...}}}}, ...])` nhận tối đa {batch} lời gọi, trả '
    "về list kết quả đúng thứ tự đã viết; mỗi phần tử là "
    '`{{"ok": True, "output": văn_bản}}` hoặc `{{"ok": False, "error": lời_lỗi}}`, và một lời '
    "gọi lỗi không làm hỏng các lời gọi còn lại. Mỗi lời gọi trong lô vẫn tính vào {calls} lời "
    "gọi đó. Ví dụ:\n"
    "{example}\n"
    "`store(khoá, giá_trị)` giữ một giá trị JSON và `load(khoá)` đọc lại ở lần chạy sau (chưa có "
    "thì None); chỉ giữ khi script chạy xong không lỗi, riêng cho cuộc trò chuyện hoặc job này.\n"
    "Đây là một phần của Python: biến, if/for/while, hàm, list/dict/set/tuple, f-string, "
    "comprehension, try/except, `json`, và len, str, int, float, bool, range, enumerate, zip, "
    "sorted, reversed, min, max, sum, any, all, abs, round, isinstance. Không có import, class, "
    "luỹ thừa `**`, `del`, `with`, đọc thuộc tính (chỉ gọi phương thức của str/list/dict/set), "
    "file hay mạng.{builtins}{mcp}\n"
)
SCRIPT_DESCRIPTION = (
    "Chạy một đoạn script Python ngắn để gọi nhiều công cụ chỉ đọc rồi tự lọc, gộp kết quả; "
    + _SCRIPT_HOW
    + "Công cụ phải hỏi trước hoặc có ghi dữ liệu thì không gọi được từ script: gọi trực tiếp."
)
# For an agent whose scripts may also call the tools that change things (`script_calls:
# gated`): the lists above then name those too.
SCRIPT_DESCRIPTION_GATED = (
    "Chạy một đoạn script Python ngắn để gọi nhiều công cụ rồi tự lọc, gộp kết quả; "
    + _SCRIPT_HOW
    + "Script của bạn gọi được cả công cụ ghi dữ liệu hay chạy lệnh. Cổng duyệt xét từng lời "
    "gọi như vậy trước khi nó chạy, y như khi gọi trực tiếp. Script không bao giờ chờ người "
    "dùng: lời gọi nào cổng phải hỏi thì script dừng ngay ở đó, khi ấy hãy gọi công cụ đó "
    "trực tiếp, ngoài script, để người dùng được hỏi. Lô có lời gọi ghi thì chạy lần lượt "
    "theo thứ tự đã viết. Lời gọi lỗi (ví dụ lệnh shell thoát với mã khác 0) ném lỗi bắt "
    "được bằng try/except: đã bắt thì in lỗi ra, đừng lặng lẽ bỏ qua. Công cụ luôn phải hỏi "
    "người dùng thì vẫn gọi trực tiếp."
)
SCRIPT_BUILTINS = "\nCông cụ có sẵn gọi được từ script (tham số như khi gọi trực tiếp):\n{lines}"
SCRIPT_MCP = (
    "\nCông cụ MCP gọi được từ script (cần tham số chi tiết thì tra bằng tools.describe):\n{lines}"
)
# Closes whichever list is the last: what is counted may be of either kind.
SCRIPT_MORE = "- … và {count} công cụ nữa, tìm bằng tools.search."
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
# For an agent whose scripts may call the tools that change things: one that waits for a
# person whatever the conversation allows is still not a script's.
SCRIPT_ALWAYS_ASKS = "`{name}` luôn phải hỏi người dùng nên không gọi được từ script: {instead}."
# A call the approval gate did not let run (`script/gate.py`). None says what the call was
# asked to do: a command may hold a secret, and the answer is kept with the run.
SCRIPT_GATE_ASK_LIST = (
    "`{name}` chưa chạy: lệnh khớp mẫu cần duyệt `{pattern}`, mà script không chờ người dùng. "
    "Gọi `{name}` trực tiếp, ngoài script, để người dùng được hỏi."
)
SCRIPT_GATE_ASKS = (
    "`{name}` chưa chạy: cuộc trò chuyện này cần người dùng duyệt lời gọi đó trước, mà script "
    "không chờ người dùng. Gọi `{name}` trực tiếp, ngoài script, để người dùng được hỏi."
)
SCRIPT_GATE_DENIED = (
    "`{name}` không chạy: agent này không được chạy lệnh chứa `{pattern}`. Đừng tìm đường khác "
    "để chạy; dừng lại và nói rõ với người dùng cần làm gì, vì sao."
)
SCRIPT_GATE_NO_TURN = "`{name}` không chạy: script không thuộc lượt nào nên không duyệt được."
# What to do instead, for a tool told up front and for one that waits to be found.
SCRIPT_CALL_DIRECTLY = "gọi trực tiếp"
SCRIPT_LOAD_THEN_CALL = "nạp bằng tool_search rồi gọi trực tiếp"
SCRIPT_TOO_MANY_CALLS = "Script đã dùng quá {most} lời gọi. Gộp việc lại hoặc chia nhiều script."

# How a run ends when it does not end well.
SCRIPT_SYNTAX = "Lỗi cú pháp ở dòng {line}: {error}"
SCRIPT_REFUSED = "Dòng {line}: {why}"
SCRIPT_UNSUPPORTED = "`{what}` không dùng được trong script."
SCRIPT_NO_ATTRIBUTE = (
    "`.{name}` không đọc được: script chỉ gọi phương thức (`x.{name}(...)`), không đọc thuộc tính."
)
# Ends a tool's answer that was cut for the script, when the whole of it was kept.
SCRIPT_ANSWER_KEPT = (
    '\n[còn {left} ký tự, đọc tiếp bằng tools.tool_output_read(id="{id}", offset={offset})]'
)
SCRIPT_ERROR = "Lỗi ở dòng {line}: {error}"
SCRIPT_HALTED = "Dừng ở dòng {line}: {reason}"

# Limits.
SCRIPT_OUT_OF_STEPS = "script chạy quá {most} bước. Xử lý ít dữ liệu hơn hoặc bỏ vòng lặp thừa."
SCRIPT_OUT_OF_ROOM = "script tạo ra quá nhiều dữ liệu. Lọc bớt trước khi gom lại."
# Stands where the middle of what a script printed was left out: the start and the end stay.
SCRIPT_OUTPUT_DROPPED = (
    "\n…[script in ra {total} ký tự, bỏ {dropped} ký tự ở giữa. "
    "Chỉ in phần cần, đã gộp hoặc lọc.]…\n"
)
# The scripts of one turn share this count; the turn ends with the script that passes it.
SCRIPT_TURN_CALLS_SPENT = "lượt đã dùng hết {most} lời gọi lồng."
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
