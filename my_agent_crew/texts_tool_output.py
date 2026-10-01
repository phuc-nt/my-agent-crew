"""Strings about tool output and tool calls (`tool_output_read`, arguments that did not
parse), split out of `texts` so neither file outgrows its budget. Import them from
`my_agent_crew.texts`, which re-exports every name here."""

TOOL_OUTPUT_READ_DESCRIPTION = (
    "Đọc lại toàn bộ kết quả gốc của một lời gọi công cụ trước đó trong CHÍNH cuộc trò chuyện"
    " này, theo id của lời gọi đó — dùng khi kết quả hiển thị đã bị rút gọn hoặc lược bớt."
    " offset tính bằng ký tự (mặc định 0), limit là số ký tự tối đa mỗi lần đọc."
)
TOOL_OUTPUT_READ_PARAM_ID = "Id của lời gọi công cụ cần đọc lại (tool_call_id)."
TOOL_OUTPUT_READ_PARAM_OFFSET = "Vị trí ký tự bắt đầu đọc, mặc định 0."
TOOL_OUTPUT_READ_PARAM_LIMIT = "Số ký tự tối đa trả về trong lần đọc này."
# The pointer a spilled output leaves behind, read by the model as an instruction: this
# exact id, passed to this exact tool, is how the rest of a cut output comes back.
TOOL_OUTPUT_POINTER = "\n[bản đầy đủ {chars} ký tự: gọi tool_output_read id={id} để đọc tiếp]"
# Ends a spill file whose original was larger than the on-disk cap.
TOOL_OUTPUT_SPILL_CAPPED = "\n…[đã cắt ở 5 MB, phần còn lại không được lưu]"
TOOL_OUTPUT_NOT_FOUND = "Không có kết quả công cụ nào với id {id} trong cuộc trò chuyện này."
# More than one row shares this id (see openai_compat's uuid fix): guessing which one the
# caller means would silently answer for the wrong call, so this refuses instead.
TOOL_OUTPUT_AMBIGUOUS = (
    "Id {id} khớp nhiều hơn một kết quả trong cuộc trò chuyện này, không thể đọc lại an toàn."
)
TOOL_OUTPUT_SOURCE_ORIGINAL = "bản gốc chưa rút gọn"
# The DB copy may itself already be the shaped (shortened) text the model first saw, when
# no spill file survived (swept, or the tool ran before this feature shipped).
TOOL_OUTPUT_SOURCE_STORED = "bản lưu trong cuộc trò chuyện (có thể đã bị rút gọn)"
TOOL_OUTPUT_READ_HEADER = "[{source}, {offset}-{end}/{total} ký tự]\n"
TOOL_OUTPUT_READ_MORE = (
    "\n[còn {remaining} ký tự — gọi lại tool_output_read id={id} offset={next_offset} để đọc tiếp]"
)
TOOL_OUTPUT_READ_DONE = "\n[đã đọc hết]"
# A tool call whose arguments were not a JSON object, so it was not run. `detail` is the
# English diagnosis from the llm layer: length, where the JSON broke, the text around it.
# The advice stays generic because not every agent has the tools a long document needs.
TOOL_ARGS_INVALID = (
    "Không chạy {name}: tham số gửi lên không phải một JSON object hợp lệ nên đã bị bỏ qua."
    " Hãy gửi lại lời gọi này. Trong chuỗi JSON, xuống dòng phải viết là \\n và dấu nháy kép"
    ' là \\"; nội dung dài thì gửi phần khung trước rồi bổ sung dần từng phần.\n'
    "Chi tiết: {detail}"
)
