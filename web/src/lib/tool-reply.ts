/**
 * A stored tool message carries no flag for success, so the thread tells a refused or a
 * failed call from a finished one by how its reply opens. A file or a search hit may quote
 * the same words further in: only a reply that opens with them counts.
 *
 * The server writes every one of these sentences, and nothing at runtime reads both sides:
 * `tests/test_tool_reply_openings.py` holds each to the server's own constant.
 */

import { parseDelegateResult } from "./delegate-result";

/** Shared by a refusal and by an approval nobody answered in time. */
const DENIED = "Người dùng đã TỪ CHỐI";
/**
 * Each as far as its fixed words go: up to the first thing the server fills in, or the whole
 * sentence when it fills in nothing. In order: the tool raised or crashed, no tool has the
 * name, a kit hook stopped it, its arguments were not valid JSON or were cut off, the turn was
 * out of steps, the turn was stopped for repeating itself, its id had been approved for
 * another call, the conversation was branched before it ran, the run was cut before it answered.
 */
const FAILED = [
  "Công cụ lỗi: ",
  "Không có công cụ tên ",
  "Hook chặn ",
  "Không chạy ",
  "Không chạy: lượt đã hết số bước tối đa nên dừng trước lệnh này.",
  "Không chạy: lệnh này đã được gọi y hệt nhiều lần liên tiếp nên lượt bị dừng tại đây.",
  "Lời gọi này trùng id với một lời gọi khác đã được duyệt cho một việc khác, nên không dùng lại quyết định đó. Hãy gọi lại nếu vẫn cần.",
  "Lệnh này chưa chạy vì hội thoại đã được rẽ nhánh trước khi nó kết thúc. Gọi lại nếu vẫn cần.",
  "Lời gọi này bị ngắt giữa chừng: không rõ nó đã chạy hay chưa. Nếu vẫn cần, hãy kiểm tra trước rồi mới gọi lại.",
];

// A `delegate` whose wait for the child ran out fails with a result shaped like any other, so
// it has no opening of its own. Its outcome line is the one a child that stopped short is
// reported under too, and the tool does not fail the call for that; what tells the two apart
// is the sentence the body opens with. Each is a one-line constant the Python tests read
// (`tests/test_tool_reply_delegate_wait.py`).
const DELEGATE = "delegate";
const NOT_FINISHED = "failed";
const WAIT_RAN_OUT = "Hết thời gian chờ agent con. Xem cuộc ";
/** Opens the count of the canvases a result left out, which stands as a paragraph before the body. */
const LEFT_OUT = "(+";

function waitRanOut(reply: string): boolean {
  const result = parseDelegateResult(reply);
  if (result?.outcome !== NOT_FINISHED) return false;
  const [first, second = ""] = result.reply.split("\n\n");
  return (first.startsWith(LEFT_OUT) ? second : first).startsWith(WAIT_RAN_OUT);
}

// A script that was stopped where it stood fails with whatever it had printed and then, on
// a line of its own, where it was stopped and why (`script/tool.py`). So the sentence does
// not open the reply: it is its last line, and a script may print the same words on any line
// before it. The sentence is `texts_script.SCRIPT_HALTED`, as far as its fixed words go; the
// number of the line follows them, then a colon and the reason, which is one line long.
const SCRIPT = "tool_script";
const SCRIPT_HALTED = "Dừng ở dòng ";
const LINE_AND_REASON = /^\d+: /;

function scriptHalted(reply: string): boolean {
  const last = reply.slice(reply.lastIndexOf("\n") + 1);
  return last.startsWith(SCRIPT_HALTED) && LINE_AND_REASON.test(last.slice(SCRIPT_HALTED.length));
}

export const isDenied = (reply: string): boolean => reply.startsWith(DENIED);

/** The status of a call to the tool `name` whose stored reply is `reply`. */
export function storedStatus(name: string, reply: string): "denied" | "failed" | "done" {
  if (isDenied(reply)) return "denied";
  if (name === DELEGATE && waitRanOut(reply)) return "failed";
  if (name === SCRIPT && scriptHalted(reply)) return "failed";
  return FAILED.some((opening) => reply.startsWith(opening)) ? "failed" : "done";
}
