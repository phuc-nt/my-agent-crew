/**
 * What became of a tool call, told from how its reply opens. A stored message carries no flag
 * for success, so a thread read back from the server has only these openings to tell by.
 * Nothing at runtime reads both sides: `tests/test_tool_reply_openings.py` holds each opening
 * to the server's own string, so neither side is reworded alone.
 */

/** Shared by a refusal and by an approval nobody answered in time. */
const DENIED = "Người dùng đã TỪ CHỐI";
/** The registry's three: the tool raised or crashed, no tool has the name, a kit hook stopped it. */
const FAILED = ["Công cụ lỗi: ", "Không có công cụ tên ", "Hook chặn "];

export const isDenied = (reply: string): boolean => reply.startsWith(DENIED);

/** The status of a call whose stored reply is `reply`. */
export function storedStatus(reply: string): "denied" | "failed" | "done" {
  if (isDenied(reply)) return "denied";
  return FAILED.some((opening) => reply.startsWith(opening)) ? "failed" : "done";
}
