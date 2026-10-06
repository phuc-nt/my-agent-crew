import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import type { AgentEvent } from "../api/types";
import type { CanvasLinks } from "../components/canvas/canvas-card";
import { ToolCallCard } from "../components/tool-call-card";
import { vi } from "../i18n/vi";
import { storedMessage } from "../test/fake-backend";
import { emptyThread, itemsFromMessages, threadReducer, type ThreadItem } from "./thread-reducer";

type Tool = Extract<ThreadItem, { kind: "tool" }>;

const STEPS = "Không chạy: lượt đã hết số bước tối đa nên dừng trước lệnh này.";
const LOOP = "Không chạy: lệnh này đã được gọi y hệt nhiều lần liên tiếp nên lượt bị dừng tại đây.";
const MISMATCH = "Lời gọi này trùng id với một lời gọi khác đã được duyệt cho một việc khác, nên không dùng lại quyết định đó. Hãy gọi lại nếu vẫn cần.";
const BRANCHED = "Lệnh này chưa chạy vì hội thoại đã được rẽ nhánh trước khi nó kết thúc. Gọi lại nếu vẫn cần.";
const CUT_SHORT = "Lời gọi này bị ngắt giữa chừng: không rõ nó đã chạy hay chưa. Nếu vẫn cần, hãy kiểm tra trước rồi mới gọi lại.";
const NOT_JSON = "Không chạy artifact_create: tham số gửi lên không phải một JSON object hợp lệ nên đã bị bỏ qua. Hãy gửi lại lời gọi này. Trong chuỗi JSON, xuống dòng phải viết là \\n và dấu nháy kép là \\\"; nội dung dài thì gửi phần khung trước rồi bổ sung dần từng phần.\nChi tiết: 40 chars; Unterminated string starting at char 12";
const CUT_OFF = "Không chạy artifact_create: câu trả lời chạm giới hạn độ dài đầu ra khi lời gọi này còn đang viết, nên tham số bị cắt và đã bị bỏ qua. Đừng gửi lại nguyên văn: lần gửi lại sẽ bị cắt đúng chỗ cũ. Chia nội dung thành nhiều lời gọi nhỏ hơn, gửi phần khung trước rồi bổ sung dần.\nChi tiết: cut off at the output limit; 51 chars; cut off at char 51";

// A `delegate` result as the tool writes it: the header, the outcome, a line for each canvas
// the child wrote, a blank line, then the body a paragraph at a time.
const HEADER = "conversation=c9 status=awaiting_approval spent=$0.0125 steps=3";
const TIMED_OUT = "outcome=failed reason=timeout";
const WAITED = "Hết thời gian chờ agent con. Xem cuộc c9 để biết nó đang ở đâu.";
const CANVASES = ["[artifact 00ff00ff00ff v2] Báo cáo tuần", "[artifact 0123456789ab v1] Phụ lục"];
const LEFT_OUT = "(+2 canvas khác, xem bằng artifact_list)";
const STOPPED_SHORT = "Agent con CHƯA làm xong (halted: max_steps). Câu trả lời bên dưới có thể dở dang, đừng đọc nó như kết luận. Kể lại cho người dùng; đừng giao lại việc này với quyền rộng hơn.\nNó chưa chạy thành công lệnh nào.";
const result = (outcome: string, canvases: string[], ...body: string[]) => [HEADER, outcome, ...canvases, "", body.join("\n\n")].join("\n");

// Every way the server fails a call, each reply as it writes it and under the tool it was for.
// A stored message has no flag for success: the reply is all the thread has to go by.
const FAILED: [how: string, tool: string, reply: string][] = [
  ["the tool raised", "artifact_export", "Công cụ lỗi: Không ghi được notes/thuc-don.md. Tệp cũ ở đó, nếu có, còn nguyên."],
  ["no tool has the name", "artifact_exprot", "Không có công cụ tên artifact_exprot."],
  ["a kit hook stopped it", "workspace_write", "Hook chặn workspace_write: ngoài giờ làm việc"],
  ["its arguments were not valid", "artifact_create", NOT_JSON],
  ["its arguments were cut off", "artifact_create", CUT_OFF],
  ["the turn was out of steps", "shell_run", STEPS],
  ["the turn was stopped for repeating itself", "shell_run", LOOP],
  ["its id had been approved for another call", "workspace_write", MISMATCH],
  ["the wait for a handed-off task ran out", "delegate", result(TIMED_OUT, [], WAITED)],
  ["the conversation was branched before it ran", "workspace_read", BRANCHED],
  ["the run was cut before it answered", "shell_run", CUT_SHORT],
];
// The last two are written into a thread nobody is watching, so no reply of theirs ever arrives.
const ARRIVING = FAILED.slice(0, 9);
// All but the handed-off task, which is known by more than how its reply opens.
const BY_OPENING = FAILED.filter(([, tool]) => tool !== "delegate");

const call = (tool: string) => ({ id: "tc", name: tool, arguments: {} });

function readBack(tool: string, reply: string): ThreadItem[] {
  return itemsFromMessages([
    storedMessage("assistant", "", { tool_calls: [call(tool)] }),
    storedMessage("tool", reply, { tool_call_id: "tc" }),
  ]);
}

function arrived(tool: string, reply: string, ok: boolean): ThreadItem[] {
  const events: AgentEvent[] = [
    { type: "assistant_message", message_id: "a", content: "", tool_calls: [call(tool)], provider: null, model: null, cost_usd: null },
    { type: "tool_call", tool_call_id: "tc", name: tool, arguments: {} },
    { type: "tool_result", tool_call_id: "tc", name: tool, ok, output: reply },
  ];
  return events.reduce((state, event) => threadReducer(state, { type: "event", event }), { ...emptyThread, busy: true }).items;
}

const settled = (tool: string, reply: string, status: string) => [{ kind: "tool", id: "tc", name: tool, arguments: {}, output: reply, status }];

function links() {
  return { titleOf: vitest.fn(() => null), isGone: vitest.fn(() => false), verify: vitest.fn(), open: vitest.fn() } satisfies CanvasLinks;
}

/** The card of the one call read back, as the thread draws it. */
function drawn(tool: string, reply: string) {
  const [item] = readBack(tool, reply);
  return render(<ToolCallCard item={item as Tool} canvas={links()} />);
}

const mark = () => document.querySelector(".tool-status");
const chips = () => screen.queryAllByTestId("delegate-canvas");

describe("a call that failed, read back from the stored thread", () => {
  it.each(FAILED)("stays failed when %s", (_how, tool, reply) => {
    expect(readBack(tool, reply)).toEqual(settled(tool, reply, "failed"));

    drawn(tool, reply);
    expect(mark()).toHaveClass("tool-status", "failed");
    expect(mark()).toHaveTextContent(vi.toolFailed);
  });

  it.each(ARRIVING)("has the status it had as it arrived when %s", (_how, tool, reply) => {
    expect(arrived(tool, reply, false)).toEqual(settled(tool, reply, "failed"));
    expect(readBack(tool, reply)).toEqual(arrived(tool, reply, false));
  });

  // A file, a search hit or a child's answer may hold the very words: only a reply that opens
  // with them is the server failing the call.
  it.each(BY_OPENING)("is not a reply that only holds the words further in, as when %s", (_how, tool, reply) => {
    for (const quoted of [`notes/nhat-ky.md, dòng 3: ${reply}`, `\n${reply}`, ` ${reply}`]) {
      expect(readBack(tool, quoted), quoted).toEqual(settled(tool, quoted, "done"));
      expect(readBack(tool, quoted), quoted).toEqual(arrived(tool, quoted, true));
    }
  });

  it.each([
    "Không chạy", // the words alone, with no tool named after them
    "Không chạy: lượt này dừng ở đây.", // goes on as neither sentence does
    "không chạy artifact_create: chữ thường",
    STEPS.slice(0, -1),
    LOOP.slice(0, -1),
    MISMATCH.slice(0, -1),
    BRANCHED.slice(0, -1),
    CUT_SHORT.slice(0, -1),
    "Lời gọi này đã chạy xong.",
    "Lệnh này chưa chạy.",
    WAITED, // the sentence a wait ends with, from a tool that hands nothing off
    result(TIMED_OUT, CANVASES, WAITED),
  ])("reads a reply that only resembles one as a call that finished: %j", (reply) => {
    expect(readBack("workspace_read", reply)).toEqual(settled("workspace_read", reply, "done"));

    drawn("workspace_read", reply);
    expect(mark()).toHaveClass("tool-status", "done");
    expect(mark()).toHaveTextContent(vi.toolDone);
  });
});

describe("a handed-off task whose wait ran out, read back from the stored thread", () => {
  // The result has the lines of any other, so it is known by its outcome and by the sentence
  // its body opens with, which the count of the canvases left out may stand before.
  const WAITS: [where: string, reply: string, canvases: number][] = [
    ["alone under the blank line", result(TIMED_OUT, [], WAITED), 0],
    ["under the canvases the child had written", result(TIMED_OUT, CANVASES, WAITED), 2],
    ["past the count of the canvases left out", result(TIMED_OUT, CANVASES, LEFT_OUT, WAITED), 2],
    ["as stored before a result named canvases", [HEADER, TIMED_OUT, WAITED].join("\n"), 0],
  ];

  it.each(WAITS)("is failed, and still names its canvases, with the sentence %s", (_where, reply, canvases) => {
    expect(readBack("delegate", reply)).toEqual(settled("delegate", reply, "failed"));
    expect(readBack("delegate", reply)).toEqual(arrived("delegate", reply, false));

    drawn("delegate", reply);
    expect(mark()).toHaveClass("tool-status", "failed");
    expect(screen.getByTestId("delegate-status")).toHaveTextContent(vi.delegateOutcome.failed);
    expect(screen.getByTestId("delegate-reason")).toHaveTextContent(vi.delegateTimeout);
    expect(chips()).toHaveLength(canvases);
  });

  // The tool does not fail the call for any of these: a child that stopped short is reported
  // under the same outcome line, and a child may say anything, the sentence included.
  it.each([
    ["a child stopped short", result("outcome=failed reason=max_steps", CANVASES, STOPPED_SHORT, "Mới viết được hai mục.")],
    ["a child stopped short, for a reason that reads the same", result(TIMED_OUT, [], STOPPED_SHORT, "Mới viết được hai mục.")],
    ["a child stopped short whose answer is the sentence", result(TIMED_OUT, [], STOPPED_SHORT, WAITED)],
    ["the same past the count of the canvases left out", result(TIMED_OUT, CANVASES, LEFT_OUT, STOPPED_SHORT, WAITED)],
    ["the sentence under words of the child's own", result(TIMED_OUT, [], "Ghi chú của tôi", WAITED)],
    ["the sentence under words that hold a count further in", result(TIMED_OUT, [], "Ghi chú (+2 mục mới)", WAITED)],
    ["the sentence quoted further in the body", result(TIMED_OUT, [], `Nó báo: ${WAITED}`)],
    ["the sentence quoted further in, past the count of the canvases left out", result(TIMED_OUT, CANVASES, LEFT_OUT, `Nó báo: ${WAITED}`)],
    ["the sentence past two counts", result(TIMED_OUT, [], LEFT_OUT, LEFT_OUT, WAITED)],
    ["a child that finished and answered with the sentence", result("outcome=done", CANVASES, WAITED)],
    ["a child that was refused and answered with it", result("outcome=blocked reason=workspace_write denied", [], WAITED)],
    ["a result stored before the outcome line, answering with it", `${HEADER}\n${WAITED}`],
    ["the sentence with no result above it", WAITED],
    ["a result quoted under a line of the child's own", `Đã hỏi lại:\n${result(TIMED_OUT, CANVASES, WAITED)}`],
  ])("is not %s", (_what, reply) => {
    expect(readBack("delegate", reply)).toEqual(settled("delegate", reply, "done"));
    expect(readBack("delegate", reply)).toEqual(arrived("delegate", reply, true));

    drawn("delegate", reply);
    expect(mark()).toHaveClass("tool-status", "done");
  });
});

describe("a script that did not run to its end, read back from the stored thread", () => {
  // `tool_script` opens the result of such a run with a line of its own, then whatever the
  // script had printed, then why it ended. The opening is all that tells it from a script that
  // ran well, which prints what it likes.
  const DID_NOT_END = "Script không chạy xong.";
  const ASKS_FIRST = "Dừng ở dòng 2: `mcp__cards__add_card` phải hỏi trước hoặc có ghi dữ liệu nên không gọi được từ script: nạp bằng tool_search rồi gọi trực tiếp.";
  const ENDED: [how: string, said: string][] = [
    ["stopped at a call it may not make", ASKS_FIRST],
    ["stopped under what it had printed, a blank line in it", `3 thẻ\n\n- Mua sữa\n${ASKS_FIRST}`],
    ["stopped at a limit", "Dừng ở dòng 14: script chạy quá 2000000 bước. Xử lý ít dữ liệu hơn hoặc bỏ vòng lặp thừa."],
    ["broken by an error nothing caught", "3 thẻ\nLỗi ở dòng 4: chưa có tên `total`"],
    ["broken by an error of several lines", "Lỗi ở dòng 3: [MCP cards] không đọc được thẻ\nthử lại sau\n(mã 503)"],
    ["not a script that can be read", "Lỗi cú pháp ở dòng 1: '(' was never closed"],
    ["refused before it ran", "Dòng 1: script không dùng được import."],
    ["out of time", "Script bị dừng: quá 60 giây mà chưa xong."],
    ["ended with nothing said of it", ""],
  ];
  const stored = (said: string) => (said ? `${DID_NOT_END}\n${said}` : DID_NOT_END);

  it.each(ENDED)("is failed, as it was when it arrived, when it was %s", (_how, said) => {
    const reply = stored(said);
    expect(readBack("tool_script", reply)).toEqual(settled("tool_script", reply, "failed"));
    expect(readBack("tool_script", reply)).toEqual(arrived("tool_script", reply, false));

    drawn("tool_script", reply);
    expect(mark()).toHaveClass("tool-status", "failed");
    expect(mark()).toHaveTextContent(vi.toolFailed);
  });

  // A script that ran to its end prints what it likes, the words a failure is told in
  // included: only the line the tool itself opens the result with says it did not.
  it.each([
    ["printed its result", "3 thẻ\n- Mua sữa"],
    ["printed nothing", "(script chạy xong, không in ra gì: dùng print để lấy kết quả)"],
    ["printed where one would have been stopped", ASKS_FIRST],
    ["printed that under what it had found", `3 thẻ\n${ASKS_FIRST}`],
    ["printed a line number and a reason", "Dòng 1: ba thẻ"],
    ["printed an error it caught", "Lỗi ở dòng 4: chưa có tên `total`\nđã thử lại"],
    ["printed the opening further down", `3 thẻ\n${DID_NOT_END}\n${ASKS_FIRST}`],
    ["printed the opening last", `3 thẻ\n${DID_NOT_END}`],
    ["printed the opening and went on along the line", `${DID_NOT_END} Nhưng có 3 thẻ.\n${ASKS_FIRST}`],
    ["printed the opening in other letters", `${DID_NOT_END.toUpperCase()}\n${ASKS_FIRST}`],
    ["printed the opening after a blank", ` ${DID_NOT_END}\n${ASKS_FIRST}`],
    ["printed the opening after a blank and no more", `\n${DID_NOT_END}`],
  ])("is not a script that %s", (_what, reply) => {
    expect(readBack("tool_script", reply)).toEqual(settled("tool_script", reply, "done"));
    expect(readBack("tool_script", reply)).toEqual(arrived("tool_script", reply, true));

    drawn("tool_script", reply);
    expect(mark()).toHaveClass("tool-status", "done");
    expect(mark()).toHaveTextContent(vi.toolDone);
  });

  // A file, a page or another tool's answer may open with the very line: it is the script
  // tool's way of failing a call, and no other tool's.
  it.each(["workspace_read", "shell_run", "tool_search", "mcp__cards__list_cards"])("is not a reply of %s that opens the same way", (tool) => {
    for (const [how, said] of ENDED) {
      const reply = stored(said);
      expect(readBack(tool, reply), how).toEqual(settled(tool, reply, "done"));
      expect(readBack(tool, reply), how).toEqual(arrived(tool, reply, true));
    }
  });
});
