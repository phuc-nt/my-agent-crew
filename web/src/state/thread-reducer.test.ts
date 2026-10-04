import { describe, expect, it } from "vitest";
import type { AgentEvent, ConversationDetail, QueuedMessage, StoredMessage } from "../api/types";
import {
  emptyThread,
  itemsFromMessages,
  questionText,
  threadReducer,
  type ThreadItem,
  type ThreadState,
} from "./thread-reducer";

const DENIED_TEXT = "Người dùng đã TỪ CHỐI hành động này. Không thử lại cùng hành động.";
const NOTE = "[Canvas · Kế hoạch tuần]\n> chạy 5 km";

function message(partial: Partial<StoredMessage> & { role: StoredMessage["role"] }): StoredMessage {
  return {
    id: partial.id ?? `m-${Math.random()}`,
    seq: 0,
    content: "",
    tool_calls: [],
    tool_call_id: null,
    name: null,
    provider: null,
    model: null,
    cost_usd: null,
    created_at: "2026-09-19T00:00:00Z",
    ...partial,
  };
}

function detail(partial: Partial<ConversationDetail> = {}): ConversationDetail {
  return {
    id: "c1",
    agent_id: "default",
    channel: "",
    title: "t",
    created_at: "",
    updated_at: "",
    autonomous: false,
    cost_cap_usd: 1,
    summary: "",
    skills: [],
    auto_approve: [],
    parent_call_id: "",
    spent_usd: 0.2,
    unknown_cost_calls: 1,
    status: "idle",
    over_budget: false,
    messages: [],
    pending_approval: null,
    ...partial,
  };
}

function run(events: AgentEvent[], from: ThreadState = { ...emptyThread, busy: true }): ThreadState {
  return events.reduce((s, event) => threadReducer(s, { type: "event", event }), from);
}

describe("itemsFromMessages", () => {
  it("maps user, assistant text, tool calls and their results in order", () => {
    const items = itemsFromMessages([
      message({ id: "u1", role: "user", content: "hi" }),
      message({
        id: "a1",
        role: "assistant",
        content: "let me look",
        model: "m",
        tool_calls: [{ id: "tc1", name: "read_file", arguments: { path: "a.txt" } }],
      }),
      message({ id: "t1", role: "tool", tool_call_id: "tc1", content: "file body" }),
      message({ id: "a2", role: "assistant", content: "done" }),
    ]);
    expect(items.map((i) => i.kind)).toEqual(["user", "assistant", "tool", "assistant"]);
    expect(items[2]).toMatchObject({ name: "read_file", output: "file body", status: "done" });
    expect(items[1]).toMatchObject({ text: "let me look", model: "m" });
  });

  it("marks a tool as denied when its stored result carries the denial text", () => {
    const items = itemsFromMessages([
      message({ role: "assistant", tool_calls: [{ id: "tc", name: "run_shell", arguments: {} }] }),
      message({ role: "tool", tool_call_id: "tc", content: DENIED_TEXT }),
    ]);
    expect(items[0]).toMatchObject({ kind: "tool", status: "denied" });
  });

  // Each as the registry writes it: the tool raised, the tool crashed, no tool has the name, a
  // kit hook stopped the call. A stored message has no flag for success, only these openings.
  const FAILED_REPLIES = [
    "Công cụ lỗi: Không ghi được notes/thuc-don.md. Tệp cũ ở đó, nếu có, còn nguyên.",
    "Công cụ lỗi: ValueError",
    "Không có công cụ tên artifact_exprot.",
    "Hook chặn workspace_write: ngoài giờ làm việc",
  ];

  it.each(FAILED_REPLIES)("keeps a call that failed as failed when the thread is read back: %s", (reply) => {
    const items = itemsFromMessages([
      message({ role: "assistant", tool_calls: [{ id: "tc", name: "artifact_export", arguments: {} }] }),
      message({ role: "tool", tool_call_id: "tc", content: reply }),
    ]);
    expect(items).toEqual([
      { kind: "tool", id: "tc", name: "artifact_export", arguments: {}, output: reply, status: "failed" },
    ]);
  });

  it.each([
    "Đã xuất v1 của canvas a1b2c3d4e5f6 «Thực đơn» (12 byte) ra notes/thuc-don.md.",
    "Kết quả: Công cụ lỗi: không phải ở đầu",
    " Công cụ lỗi: sau một dấu cách",
    "Công cụ lỗi", // the words alone, with no failure after them
    "công cụ lỗi: chữ thường",
    "Không có công cụ nào cần gọi.",
    "Hook chặnworkspace_write",
    "",
  ])("reads a reply that only resembles a failure as a call that finished: %j", (reply) => {
    const items = itemsFromMessages([
      message({ role: "assistant", tool_calls: [{ id: "tc", name: "read_file", arguments: {} }] }),
      message({ role: "tool", tool_call_id: "tc", content: reply }),
    ]);
    expect(items[0]).toMatchObject({ kind: "tool", status: "done", output: reply });
  });

  it("gives a reply the same status read back as it had when it arrived", () => {
    const replies = [...FAILED_REPLIES, DENIED_TEXT];
    const calls = replies.map((_, at) => ({ id: `tc${at}`, name: "run_shell", arguments: {} }));
    const live = run([
      { type: "assistant_message", message_id: "a", content: "", tool_calls: calls, provider: null, model: null, cost_usd: null },
      ...calls.map((call) => ({ type: "tool_call" as const, tool_call_id: call.id, name: call.name, arguments: {} })),
      ...replies.map((output, at) => ({ type: "tool_result" as const, tool_call_id: `tc${at}`, name: "run_shell", ok: false, output })),
    ]);
    const stored = itemsFromMessages([
      message({ role: "assistant", tool_calls: calls }),
      ...replies.map((content, at) => message({ role: "tool", tool_call_id: `tc${at}`, content })),
    ]);
    const statuses = (items: ThreadItem[]) => items.map((item) => (item.kind === "tool" ? item.status : item.kind));
    expect(statuses(stored)).toEqual(["failed", "failed", "failed", "failed", "denied"]);
    expect(statuses(stored)).toEqual(statuses(live.items));
  });

  it("skips system messages and assistant messages with no content or calls", () => {
    expect(itemsFromMessages([message({ role: "system", content: "x" }), message({ role: "assistant" })])).toEqual([]);
  });

  it("carries the canvas note a user message was stored with, and nothing for one stored without", () => {
    const items = itemsFromMessages([
      message({ id: "u1", role: "user", content: "sửa chỗ này", context: NOTE }),
      message({ id: "u2", role: "user", content: "không kèm gì" }),
      message({ id: "u3", role: "user", content: "ghi chú rỗng", context: "" }),
    ]);
    expect(items[0]).toEqual({ kind: "user", id: "u1", text: "sửa chỗ này", context: NOTE });
    // No key at all, not an empty one: the thread draws a chip wherever `context` is set.
    expect(items[1]).not.toHaveProperty("context");
    expect(items[2]).not.toHaveProperty("context");
  });
});

describe("threadReducer loaded", () => {
  it("restores budget counters and a pending approval as an awaiting tool", () => {
    const state = threadReducer(
      emptyThread,
      {
        type: "loaded",
        detail: detail({
          messages: [message({ role: "assistant", tool_calls: [{ id: "tc", name: "write_file", arguments: { path: "x" } }] })],
          pending_approval: {
            id: "ap1",
            conversation_id: "c1",
            message_id: "m",
            tool_call_id: "tc",
            tool_name: "write_file",
            arguments: { path: "x" },
            status: "pending",
            created_at: "",
            expires_at: "2026-09-20T03:10:00Z",
            resolved_at: null,
          },
        }),
      },
    );
    expect(state.spentUsd).toBe(0.2);
    expect(state.unknownCostCalls).toBe(1);
    // No `kind` on the row: written before questions existed, so it is a tool call. Read
    // as a question it would get a card whose only route the server refuses.
    expect(state.pending).toEqual({
      approvalId: "ap1",
      toolCallId: "tc",
      name: "write_file",
      arguments: { path: "x" },
      expiresAt: "2026-09-20T03:10:00Z",
      kind: "tool",
      options: [],
    });
    expect(state.items[0]).toMatchObject({ kind: "tool", status: "awaiting" });
    expect(state.busy).toBe(false);
  });

  it("carries the kind and the choices of a question through the live event", () => {
    // Without these the card cannot tell a question from a tool call, and the person is
    // offered Allow/Refuse for a row the server will only accept an answer on.
    const event: AgentEvent = {
      type: "approval_required",
      approval_id: "ap2",
      tool_call_id: "tc2",
      name: "ask_user",
      arguments: { question: "Dời hạn sang thứ sáu?" },
      reason: "",
      expires_at: "",
      kind: "question",
      options: ["có", "không"],
    };
    const state = threadReducer(emptyThread, { type: "event", event });
    expect(state.pending?.kind).toBe("question");
    expect(state.pending?.options).toEqual(["có", "không"]);
    expect(questionText(state.pending!)).toBe("Dời hạn sang thứ sáu?");
  });

  it("reads a question waiting on a reloaded conversation", () => {
    const state = threadReducer(emptyThread, {
      type: "loaded",
      detail: detail({
        pending_approval: {
          id: "ap3",
          conversation_id: "c1",
          message_id: "m",
          tool_call_id: "tc3",
          tool_name: "ask_user",
          arguments: { question: "Đặt tên gì?" },
          status: "pending",
          created_at: "",
          expires_at: null,
          resolved_at: null,
          kind: "question",
          options: [],
        },
      }),
    });
    expect(state.pending?.kind).toBe("question");
    expect(questionText(state.pending!)).toBe("Đặt tên gì?");
  });

  it("keeps which ask pattern stopped a command on a reloaded conversation", () => {
    // Opened after an unattended run paused, the chat never saw the live event: the stored
    // request is all there is to say why an autonomous conversation stopped.
    const state = threadReducer(emptyThread, {
      type: "loaded",
      detail: detail({
        pending_approval: {
          id: "ap4",
          conversation_id: "c1",
          message_id: "m",
          tool_call_id: "tc4",
          tool_name: "shell_run",
          arguments: { command: "rm -rf build" },
          status: "pending",
          created_at: "",
          expires_at: null,
          resolved_at: null,
          reason: "khớp mẫu cần duyệt: `rm -rf`",
        },
      }),
    });
    expect(state.pending?.reason).toBe("khớp mẫu cần duyệt: `rm -rf`");
  });
});

describe("threadReducer streaming turn", () => {
  it("accumulates deltas then replaces them with the final assistant message", () => {
    const mid = run([
      { type: "text_delta", text: "Xin " },
      { type: "text_delta", text: "chào" },
    ]);
    expect(mid.streaming).toBe("Xin chào");
    const end = run(
      [
        { type: "assistant_message", message_id: "a1", content: "Xin chào", tool_calls: [], provider: "p", model: "m", cost_usd: 0.01 },
        { type: "done", spent_usd: 0.01, unknown_cost_calls: 0 },
      ],
      mid,
    );
    expect(end.streaming).toBeNull();
    expect(end.busy).toBe(false);
    expect(end.spentUsd).toBe(0.01);
    expect(end.items).toEqual([{ kind: "assistant", id: "a1", text: "Xin chào", model: "m" }]);
  });

  it("tracks a tool call from announcement through result", () => {
    const state = run([
      { type: "assistant_message", message_id: "a", content: "", tool_calls: [{ id: "tc", name: "list_dir", arguments: { path: "." } }], provider: null, model: null, cost_usd: null },
      { type: "tool_call", tool_call_id: "tc", name: "list_dir", arguments: { path: "." } },
      { type: "tool_result", tool_call_id: "tc", name: "list_dir", ok: false, output: "Công cụ lỗi: nope" },
    ]);
    expect(state.items).toHaveLength(1);
    expect(state.items[0]).toMatchObject({ kind: "tool", status: "failed", output: "Công cụ lỗi: nope" });
  });

  it("pauses on approval_required and resumes when the tool result arrives", () => {
    const paused = run([
      { type: "assistant_message", message_id: "a", content: "", tool_calls: [{ id: "tc", name: "write_file", arguments: {} }], provider: null, model: null, cost_usd: null },
      { type: "approval_required", approval_id: "ap", tool_call_id: "tc", name: "write_file", arguments: {}, reason: "khớp mẫu cần duyệt: `sudo `", expires_at: "2026-09-20T03:10:00Z" },
    ]);
    expect(paused.busy).toBe(false);
    expect(paused.pending?.approvalId).toBe("ap");
    expect(paused.pending?.reason).toBe("khớp mẫu cần duyệt: `sudo `");
    expect(paused.pending?.expiresAt).toBe("2026-09-20T03:10:00Z");
    expect(paused.items[0]).toMatchObject({ status: "awaiting" });
    const resumed = run([{ type: "tool_result", tool_call_id: "tc", name: "write_file", ok: true, output: DENIED_TEXT }], paused);
    expect(resumed.pending).toBeNull();
    expect(resumed.items[0]).toMatchObject({ status: "denied" });
  });

  it("surfaces halted and error events as notices and clears busy", () => {
    const halted = run([{ type: "halted", reason: "budget", spent_usd: 0.5 }]);
    expect(halted).toMatchObject({ busy: false, spentUsd: 0.5, notice: { kind: "halted", text: "budget" } });
    const errored = run([{ type: "error", message: "all routes failed" }]);
    expect(errored.notice).toEqual({ kind: "error", text: "all routes failed" });
    expect(errored.busy).toBe(false);
  });

  it("shows a route fallback as a notice while the turn keeps running", () => {
    const fell = run([{ type: "route_fallback", provider: "openrouter", model: "glm", error: "HTTP 429" }]);
    expect(fell.notice).toEqual({ kind: "fallback", text: "openrouter:glm — HTTP 429" });
    expect(fell.busy).toBe(true);
  });

  it("a thinking model shows as thinking until its first word, tool call or end", () => {
    expect(run([{ type: "thinking" }]).thinking).toBe(true);
    expect(run([{ type: "thinking" }, { type: "text_delta", text: "HRV" }]).thinking).toBe(false);
    const called = run([
      { type: "thinking" },
      { type: "tool_call", tool_call_id: "t1", name: "shell_run", arguments: {} },
    ]);
    expect(called.thinking).toBe(false);
    expect(run([{ type: "thinking" }, { type: "error", message: "x" }]).thinking).toBe(false);
  });

  it("a model_call marker changes nothing in the thread: the step timing lives on the run", () => {
    const before = run([{ type: "thinking" }]);
    expect(threadReducer(before, { type: "event", event: { type: "model_call", stage: "first_token" } })).toBe(before);
    expect(run([{ type: "model_call", stage: "sent" }]).busy).toBe(true);
  });

  it("a user_context event gives the message this tab just drew the note the server stored with it", () => {
    const earlier: ThreadItem = { kind: "user", id: "m-1", text: "câu cũ", context: "ghi chú cũ" };
    const sent = threadReducer({ ...emptyThread, items: [earlier] }, { type: "user_sent", text: "sửa chỗ này" });
    const noted = run([{ type: "user_context", context: NOTE }], { ...sent, busy: true });
    // The bubble keeps its local id: forking finds it by position, and a note changes nothing
    // about where the message stands. The message before it is left as it was.
    expect(noted.items).toEqual([earlier, { kind: "user", id: "local-1", text: "sửa chỗ này", context: NOTE }]);
    expect(noted.items[0]).toBe(earlier);
    expect(noted.busy).toBe(true);
  });

  it("a user_context event goes to the latest user message, wherever it stands in the thread", () => {
    const items: ThreadItem[] = [
      { kind: "user", id: "m-1", text: "một" },
      { kind: "user", id: "local-1", text: "hai" },
      { kind: "assistant", id: "a-1", text: "đã rõ", model: null },
    ];
    const noted = run([{ type: "user_context", context: NOTE }], { ...emptyThread, busy: true, items });
    expect(noted.items.map((it) => (it.kind === "user" ? (it.context ?? "none") : "-"))).toEqual(["none", NOTE, "-"]);
  });

  it("a user_context event leaves the thread alone when it holds no user message to give it to", () => {
    const state: ThreadState = {
      ...emptyThread,
      busy: true,
      items: [{ kind: "assistant", id: "a-1", text: "xin chào", model: null }],
    };
    const next = run([{ type: "user_context", context: NOTE }], state);
    expect(next.items).toBe(state.items);
    // The outer case clears `thinking` for every event that is not a marker; nothing else moved.
    expect(next).toEqual({ ...state, thinking: false });
  });

  it("user_sent appends locally and turn_started clears the previous notice", () => {
    const withNotice = threadReducer(emptyThread, { type: "failed", message: "x" });
    const sent = threadReducer(withNotice, { type: "user_sent", text: "hello" });
    expect(sent.items).toEqual([{ kind: "user", id: "local-0", text: "hello" }]);
    expect(sent.notice).toBeNull();
    expect(threadReducer(sent, { type: "turn_started" })).toMatchObject({ busy: true, streaming: null });
  });
});

describe("threadReducer turn end", () => {
  const twoCalls: AgentEvent = {
    type: "assistant_message",
    message_id: "a",
    content: "",
    tool_calls: [
      { id: "tc1", name: "write_file", arguments: {} },
      { id: "tc2", name: "read_file", arguments: {} },
    ],
    provider: null,
    model: null,
    cost_usd: null,
  };
  const approval: AgentEvent = {
    type: "approval_required",
    approval_id: "ap",
    tool_call_id: "tc1",
    name: "write_file",
    arguments: {},
    reason: "",
    expires_at: "",
  };
  const statuses = (s: ThreadState) => s.items.map((it) => (it.kind === "tool" ? it.status : it.kind));

  it("a turn that ends with a call still unanswered leaves it stopped, not spinning", () => {
    const cut = run([twoCalls, { type: "tool_result", tool_call_id: "tc1", name: "write_file", ok: true, output: "ok" }]);
    expect(statuses(cut)).toEqual(["done", "running"]);
    expect(statuses(threadReducer(cut, { type: "turn_finished" }))).toEqual(["done", "stopped"]);
    const failed = threadReducer(cut, { type: "failed", message: "net" });
    expect(statuses(failed)).toEqual(["done", "stopped"]);
    expect(failed.notice).toEqual({ kind: "error", text: "net" });
  });

  it("a request answered elsewhere is a note that leaves the other run's calls going", () => {
    const reloaded = { ...run([twoCalls]), busy: false };
    const handled = threadReducer(reloaded, { type: "handled" });
    expect(statuses(handled)).toEqual(["running", "running"]);
    expect(handled.notice).toEqual({ kind: "handled", text: "" });
    // A turn begun since has the thread: a note about the earlier decision would be stale.
    const next = run([twoCalls]);
    expect(threadReducer(next, { type: "handled" })).toBe(next);
  });

  it("keeps that note through the loads that follow it, until one brings a new request", () => {
    // The run the decision resumed, or the stream coming back, reads the thread again:
    // neither answers the person's click a second time.
    const noted = threadReducer({ ...run([twoCalls]), busy: false }, { type: "handled" });
    const calls = [message({ role: "assistant", tool_calls: [{ id: "tc3", name: "write_file", arguments: {} }] })];
    const again = threadReducer(noted, { type: "loaded", detail: detail({ messages: calls }) });
    expect(again.notice).toEqual({ kind: "handled", text: "" });
    const asking = detail({
      messages: calls,
      pending_approval: {
        id: "ap5",
        conversation_id: "c1",
        message_id: "m",
        tool_call_id: "tc3",
        tool_name: "write_file",
        arguments: {},
        status: "pending",
        created_at: "",
        expires_at: null,
        resolved_at: null,
      },
    });
    expect(threadReducer(again, { type: "loaded", detail: asking }).notice).toBeNull();
    // Any other note still belongs to the thread as it was before the load.
    const failed = threadReducer(noted, { type: "failed", message: "net" });
    expect(threadReducer(failed, { type: "loaded", detail: detail() }).notice).toBeNull();
  });

  it("opening another conversation starts from nothing, not even that note", () => {
    const noted = threadReducer({ ...run([twoCalls]), busy: false }, { type: "handled" });
    expect(threadReducer(noted, { type: "opened" })).toEqual(emptyThread);
  });

  it("a turn paused on a person keeps the calls queued behind the one waiting", () => {
    const ended = threadReducer(run([twoCalls, approval]), { type: "turn_finished" });
    expect(statuses(ended)).toEqual(["awaiting", "running"]);
    expect(threadReducer(ended, { type: "settled" })).toBe(ended);
  });

  it("stopping ends the turn at once, drops the spent decision and says it stopped", () => {
    // Stop pressed while the approved call streams back, and while a call still waits.
    const streaming = run([twoCalls, { type: "tool_call", tool_call_id: "tc1", name: "write_file", arguments: {} }, { type: "text_delta", text: "đang" }]);
    for (const from of [streaming, { ...run([twoCalls, approval]), busy: true }]) {
      const stopped = threadReducer(from, { type: "turn_stopped" });
      expect(stopped).toMatchObject({ busy: false, streaming: null, pending: null, notice: { kind: "stopped", text: "" } });
      expect(statuses(stopped)).toEqual(["stopped", "stopped"]);
    }
  });

  it("settling stops leftover calls only when no turn is going", () => {
    const busy = run([twoCalls]);
    expect(threadReducer(busy, { type: "settled" })).toBe(busy);
    const settled = threadReducer({ ...busy, busy: false }, { type: "settled" });
    expect(statuses(settled)).toEqual(["stopped", "stopped"]);
    expect(threadReducer(settled, { type: "settled" })).toBe(settled);
  });
});

describe("threadReducer queue and steer", () => {
  const followUp: QueuedMessage = { id: 1, kind: "follow_up", text: "sau đó thì sao?" };
  const steerItem: QueuedMessage = { id: 2, kind: "steer", text: "dừng lại đã" };

  it("loaded reads waiting from detail.queued, defaulting to empty", () => {
    const withItems = threadReducer(emptyThread, {
      type: "loaded",
      detail: detail({ queued: [followUp, steerItem] }),
    });
    expect(withItems.waiting).toEqual([followUp, steerItem]);
    const withoutField = threadReducer(emptyThread, { type: "loaded", detail: detail() });
    expect(withoutField.waiting).toEqual([]);
  });

  it("opened clears waiting along with the rest of the thread", () => {
    const loaded = threadReducer(emptyThread, {
      type: "loaded",
      detail: detail({ queued: [followUp] }),
    });
    expect(threadReducer(loaded, { type: "opened" })).toEqual(emptyThread);
  });

  it("queued adds a chip and drops the matching local bubble, but only on a text match", () => {
    const sent = threadReducer({ ...emptyThread, busy: true }, { type: "user_sent", text: followUp.text });
    const queued = threadReducer(sent, { type: "queued", item: followUp });
    expect(queued.waiting).toEqual([followUp]);
    expect(queued.items).toEqual([]);
    // A local bubble for different text (an unrelated message sent moments before) stays.
    const other = threadReducer({ ...emptyThread, busy: true }, { type: "user_sent", text: "khác hẳn" });
    const stillThere = threadReducer(other, { type: "queued", item: followUp });
    expect(stillThere.waiting).toEqual([followUp]);
    expect(stillThere.items).toEqual([{ kind: "user", id: "local-0", text: "khác hẳn" }]);
    // No local bubble at all (the busy-send path never dispatches user_sent): the chip is
    // simply added.
    const busyPath = threadReducer({ ...emptyThread, busy: true }, { type: "queued", item: followUp });
    expect(busyPath.waiting).toEqual([followUp]);
    expect(busyPath.items).toEqual([]);
  });

  it("user_unsent takes back the local bubble for that text, and only that one", () => {
    const earlier: ThreadItem = { kind: "user", id: "m-1", text: "câu cũ" };
    const sent = threadReducer(
      { ...emptyThread, items: [earlier] },
      { type: "user_sent", text: "chưa tới được server" },
    );
    expect(threadReducer(sent, { type: "user_unsent", text: "chưa tới được server" }).items).toEqual([earlier]);
    // Other words: the bubble stands for some other send, and stays.
    expect(threadReducer(sent, { type: "user_unsent", text: "khác hẳn" }).items).toBe(sent.items);
    // A message the server stored, with the same words, is not this send's bubble.
    const stored = { ...emptyThread, items: [{ kind: "user" as const, id: "m-2", text: "lặp lại" }] };
    expect(threadReducer(stored, { type: "user_unsent", text: "lặp lại" }).items).toBe(stored.items);
    // Anything after the bubble means the server has answered: it stays.
    const answered = { ...sent, items: [...sent.items, { kind: "note" as const, id: "n1", text: "đang xem" }] };
    expect(threadReducer(answered, { type: "user_unsent", text: "chưa tới được server" }).items).toBe(answered.items);
  });

  it("queue_cleared empties waiting", () => {
    const withChips = { ...emptyThread, waiting: [followUp, steerItem] };
    expect(threadReducer(withChips, { type: "queue_cleared" }).waiting).toEqual([]);
  });

  it("elsewhere sets a notice of that kind", () => {
    const state = threadReducer(emptyThread, { type: "elsewhere" });
    expect(state.notice).toEqual({ kind: "elsewhere", text: "" });
  });

  it("a steer event adds one user message and drops the oldest matching count of steer chips", () => {
    const withChips = {
      ...emptyThread,
      busy: true,
      waiting: [followUp, steerItem, { id: 3, kind: "steer" as const, text: "rồi sao nữa" }],
    };
    const steered = run([{ type: "steer", text: "chèn vào giữa", count: 1 }], withChips);
    expect(steered.items).toEqual([{ kind: "user", id: "local-0", text: "chèn vào giữa" }]);
    // The oldest steer chip is gone; the follow_up chip and the newer steer chip stay.
    expect(steered.waiting).toEqual([followUp, { id: 3, kind: "steer", text: "rồi sao nữa" }]);
  });

  it("a steer count larger than the number of steer chips only drops the steer chips there are", () => {
    const withChips = { ...emptyThread, busy: true, waiting: [followUp, steerItem] };
    const steered = run([{ type: "steer", text: "chèn", count: 5 }], withChips);
    expect(steered.waiting).toEqual([followUp]);
    expect(steered.items).toHaveLength(1);
  });

  it("a queued event reaching the reducer directly is a no-op: the hook intercepts it first", () => {
    const state = { ...emptyThread, busy: true };
    // `run` wraps every event as `threadReducer`'s outer `event` case does, which always
    // clears `thinking`; `applyEvent` itself changes nothing else for this event.
    expect(run([{ type: "queued", item_id: 9, kind: "follow_up", position: 1 }], state)).toEqual({
      ...state,
      thinking: false,
    });
  });

  it("queue_failed sets an error notice without touching busy, streaming or items", () => {
    const running = {
      ...emptyThread,
      busy: true,
      streaming: "đang trả lời",
      items: [{ kind: "user" as const, id: "local-0", text: "việc đầu tiên" }],
    };
    const failed = threadReducer(running, { type: "queue_failed", message: "hàng đầy, hãy chờ hoặc bấm Stop" });
    expect(failed.notice).toEqual({ kind: "error", text: "hàng đầy, hãy chờ hoặc bấm Stop" });
    expect(failed.busy).toBe(true);
    expect(failed.streaming).toBe("đang trả lời");
    expect(failed.items).toBe(running.items);
  });
});
