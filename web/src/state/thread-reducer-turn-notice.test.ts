import { describe, expect, it } from "vitest";
import type { AgentEvent, ConversationDetail, StoredMessage } from "../api/types";
import { emptyThread, threadReducer, type ThreadAction, type ThreadState } from "./thread-reducer";

// What a turn said of itself, that it ended in an error, stopped short, or went on by another
// route, is held by the tab alone: no stored conversation has it. A load of the conversation
// that follows the turn's own end must not take it away. One follows whenever the tab's
// opening load was overtaken by the message, and always in a tab that only read along.

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
    created_at: "2026-10-06T00:00:00Z",
    ...partial,
  };
}

function detail(messages: StoredMessage[], partial: Partial<ConversationDetail> = {}): ConversationDetail {
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
    spent_usd: 0,
    unknown_cost_calls: 0,
    status: "idle",
    over_budget: false,
    messages,
    pending_approval: null,
    ...partial,
  };
}

const act = (state: ThreadState, ...actions: ThreadAction[]) => actions.reduce(threadReducer, state);
const events = (state: ThreadState, ...said: AgentEvent[]) =>
  act(state, ...said.map((event) => ({ type: "event" as const, event })));
const loaded = (state: ThreadState, messages: StoredMessage[], partial: Partial<ConversationDetail> = {}) =>
  act(state, { type: "loaded", detail: detail(messages, partial) });

const EARLIER = [message({ id: "u0", role: "user", content: "chào" }), message({ id: "a0", role: "assistant", content: "Chào bạn" })];
const SENT = message({ id: "u1", role: "user", content: "tin mới" });
const ANSWER = message({ id: "a1", role: "assistant", content: "Đã nhận", model: "echo" });
const CALL = { id: "tc1", name: "shell_run", arguments: { command: "ls" } };

const answered: AgentEvent[] = [
  { type: "assistant_message", message_id: "a1", content: "Đã nhận", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
  { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
];

/** Each thing a turn says of itself: the events that say it, the notice they leave, and the
 *  messages the server has stored for the turn by the time it is over. */
const SAID = {
  error: {
    turn: [{ type: "error", message: "all routes failed" }],
    notice: { kind: "error", text: "all routes failed", ofTurn: true },
    stored: [SENT],
  },
  halted: {
    turn: [
      { type: "assistant_message", message_id: "a1", content: "", tool_calls: [CALL], provider: "fake", model: "echo", cost_usd: 0 },
      { type: "tool_result", tool_call_id: "tc1", name: "shell_run", ok: false, output: "Đã dừng vì lặp lại." },
      { type: "halted", reason: "loop", spent_usd: 0.3 },
    ],
    notice: { kind: "halted", text: "loop" },
    stored: [
      SENT,
      message({ id: "a1", role: "assistant", tool_calls: [CALL] }),
      message({ id: "t1", role: "tool", tool_call_id: "tc1", name: "shell_run", content: "Đã dừng vì lặp lại." }),
    ],
  },
  fallback: {
    turn: [{ type: "route_fallback", provider: "openrouter", model: "flash", error: "HTTP 502" }, ...answered],
    notice: { kind: "fallback", text: "openrouter:flash — HTTP 502" },
    stored: [SENT, ANSWER],
  },
  escalated: {
    turn: [{ type: "escalated", reason: "error", provider: "fake", model: "echo", error: "every route failed" }, ...answered],
    notice: { kind: "escalated", text: "fake:echo", reason: "error" },
    stored: [SENT, ANSWER],
  },
} satisfies Record<string, { turn: AgentEvent[]; notice: ThreadState["notice"]; stored: StoredMessage[] }>;

type Said = keyof typeof SAID;
const KINDS = Object.keys(SAID) as Said[];

/** The thread as the tab has it once its own message's turn is over: what was on screen
 *  before, the bubble of the message, and what the turn's stream brought. */
function after(kind: Said, before: ThreadState = loaded(emptyThread, EARLIER)): ThreadState {
  const sent = act(before, { type: "user_sent", text: "tin mới" }, { type: "turn_started" });
  return events(sent, ...SAID[kind].turn);
}

describe("what a turn said of itself, through a load that follows the turn's end", () => {
  it.each(KINDS)("is the notice the turn left: %s", (kind) => {
    const over = after(kind);
    expect(over.notice).toStrictEqual(SAID[kind].notice);
    expect(over.busy).toBe(false);
  });

  it.each(KINDS)("stays while the stored thread ends where the thread on screen ends: %s", (kind) => {
    const read = loaded(after(kind), [...EARLIER, ...SAID[kind].stored]);

    expect(read.notice).toStrictEqual(SAID[kind].notice);
    // The load is taken all the same: the message is the server's now, under its stored id.
    expect(read.items.map((item) => item.id)).not.toContain("local-2");
    expect(read.items.some((item) => item.kind === "user" && item.id === "u1")).toBe(true);
  });

  it.each(KINDS)("stays when that load is the first to land, and brings history the screen never had: %s", (kind) => {
    // The message went out before the conversation's opening load had answered.
    const over = after(kind, emptyThread);
    expect(over.items[0]).toMatchObject({ kind: "user", id: "local-0" });

    const read = loaded(over, [...EARLIER, ...SAID[kind].stored]);

    expect(read.notice).toStrictEqual(SAID[kind].notice);
    expect(read.items[0]).toMatchObject({ kind: "user", id: "u0" });
  });

  it.each(KINDS)("stays through every such load, not the first alone: %s", (kind) => {
    const stored = [...EARLIER, ...SAID[kind].stored];
    const read = loaded(loaded(loaded(after(kind), stored), stored), stored);

    expect(read.notice).toStrictEqual(SAID[kind].notice);
  });

  it.each(KINDS)("goes once a load brings anything after it: %s", (kind) => {
    const stored = [...EARLIER, ...SAID[kind].stored];
    const elsewhere = [message({ id: "u2", role: "user", content: "hỏi từ Telegram" }), message({ id: "a2", role: "assistant", content: "Trả lời" })];

    expect(loaded(after(kind), [...stored, ...elsewhere]).notice).toBeNull();
    expect(loaded(after(kind), [...stored, elsewhere[0]]).notice).toBeNull();
    // Kept by one load, it is still dropped by the next that brings more.
    expect(loaded(loaded(after(kind), stored), [...stored, ...elsewhere]).notice).toBeNull();
  });

  it.each(KINDS)("goes when the stored thread ends on something else of the same sort: %s", (kind) => {
    const stored = [...EARLIER, ...SAID[kind].stored];
    const last = stored[stored.length - 1];
    // The same role and the same words would be the same message; another id or other words are not.
    const other =
      last.role === "user" ? { ...last, content: "tin khác" } : last.role === "tool" ? null : { ...last, id: "a9" };
    const ends = other
      ? [...stored.slice(0, -1), other]
      : [...EARLIER, SENT, message({ id: "a9", role: "assistant", tool_calls: [{ ...CALL, id: "tc9" }] })];

    expect(loaded(after(kind), ends).notice).toBeNull();
  });

  it("goes when the thread on screen held nothing of the stored thread's end", () => {
    // A stored thread that is empty, or one cut back to before the message, ends nowhere the screen does.
    expect(loaded(after("error"), []).notice).toBeNull();
    expect(loaded(after("escalated"), EARLIER).notice).toBeNull();
    expect(loaded(after("error"), EARLIER).notice).toBeNull();
  });

  it("knows the person's own message by its words, and nothing else by them", () => {
    // The bubble has no stored id until it is loaded: its words stand for it.
    expect(loaded(after("error"), [...EARLIER, { ...SENT, id: "any-id" }]).notice).toStrictEqual(SAID.error.notice);
    // An answer with the same words under another id is another answer.
    expect(loaded(after("escalated"), [...EARLIER, SENT, { ...ANSWER, id: "a9" }]).notice).toBeNull();
    // An answer whose words happen to be the person's is not their message.
    expect(loaded(after("error"), [...EARLIER, message({ id: "a9", role: "assistant", content: "tin mới" })]).notice).toBeNull();
  });

  it("stays on a turn that ended after a note of what it was doing", () => {
    // A note is drawn as a note while it streams and stored as the call it was: one thing.
    const note = { id: "n1", name: "progress_note", arguments: { text: "Đang tìm" } };
    const over = events(
      act(loaded(emptyThread, EARLIER), { type: "user_sent", text: "tin mới" }, { type: "turn_started" }),
      { type: "assistant_message", message_id: "a1", content: "", tool_calls: [note], provider: "fake", model: "echo", cost_usd: 0 },
      { type: "tool_result", tool_call_id: "n1", name: "progress_note", ok: true, output: "ok" },
      { type: "error", message: "all routes failed" },
    );
    expect(over.items[over.items.length - 1]).toMatchObject({ kind: "note", id: "n1" });

    const read = loaded(over, [
      ...EARLIER,
      SENT,
      message({ id: "a1", role: "assistant", tool_calls: [note] }),
      message({ id: "t1", role: "tool", tool_call_id: "n1", name: "progress_note", content: "ok" }),
    ]);

    expect(read.notice).toStrictEqual(SAID.error.notice);
  });

  it("stays with the request the turn then stopped on", () => {
    const asked = events(
      act(loaded(emptyThread, EARLIER), { type: "user_sent", text: "tin mới" }, { type: "turn_started" }),
      { type: "route_fallback", provider: "openrouter", model: "flash", error: "HTTP 502" },
      { type: "assistant_message", message_id: "a1", content: "", tool_calls: [CALL], provider: "fake", model: "echo", cost_usd: 0 },
      { type: "approval_required", approval_id: "ap1", tool_call_id: "tc1", name: "shell_run", arguments: CALL.arguments, reason: "", expires_at: "2026-10-07T00:00:00Z" },
    );

    const read = loaded(asked, [...EARLIER, SENT, message({ id: "a1", role: "assistant", tool_calls: [CALL] })], {
      status: "awaiting_approval",
      pending_approval: {
        id: "ap1",
        conversation_id: "c1",
        message_id: "a1",
        tool_call_id: "tc1",
        tool_name: "shell_run",
        arguments: CALL.arguments,
        status: "pending",
        created_at: "",
        expires_at: "2026-10-07T00:00:00Z",
        resolved_at: null,
      },
    });

    expect(read.pending?.approvalId).toBe("ap1");
    expect(read.notice).toStrictEqual(SAID.fallback.notice);
  });
});

describe("an error of a request this tab made, which is not the turn's", () => {
  const stored = [...EARLIER, SENT];

  it("is not marked as the turn's own", () => {
    const failed = act(after("fallback"), { type: "failed", message: "Không tải được." });
    expect(failed.notice).toStrictEqual({ kind: "error", text: "Không tải được." });
    const refused = act(after("fallback"), { type: "queue_failed", message: "Không gửi được." });
    expect(refused.notice).toStrictEqual({ kind: "error", text: "Không gửi được." });
  });

  it("is cleared by the next load that answers, though the thread ends where it did", () => {
    const sent = act(loaded(emptyThread, EARLIER), { type: "user_sent", text: "tin mới" }, { type: "turn_started" });
    // The stream of the send broke: the tab's own failure, and the server may well go on.
    const failed = act(sent, { type: "failed", message: "Mất kết nối." });
    expect(failed.notice?.kind).toBe("error");

    expect(loaded(failed, stored).notice).toBeNull();
  });

  it("is cleared by the next load that answers after a load that failed", () => {
    const failed = act(loaded(emptyThread, stored), { type: "failed", message: "Không tải được." });
    expect(loaded(failed, stored).notice).toBeNull();
    // On a thread nothing was ever loaded into, too.
    expect(loaded(act(emptyThread, { type: "failed", message: "Không tải được." }), stored).notice).toBeNull();
    expect(loaded(act(emptyThread, { type: "failed", message: "Không tải được." }), []).notice).toBeNull();
  });

  it("is cleared by the next load that answers when a waiting message could not be taken back", () => {
    const refused = act(loaded(emptyThread, stored), { type: "queue_failed", message: "Không gỡ được." });
    expect(loaded(refused, stored).notice).toBeNull();
  });
});

describe("what the last turn said, in a tab that finds another turn going", () => {
  const watching = (running: boolean, messages: StoredMessage[]): AgentEvent => ({ type: "watching", running, detail: detail(messages) });

  it.each(KINDS)("is dropped though the stored thread ends where it did: %s", (kind) => {
    // A turn carried on after a restart, or a job's, starts with no new message: the thread
    // ends as it did, and the turn that said this is not the one now running.
    const joined = events(after(kind), watching(true, [...EARLIER, ...SAID[kind].stored]));

    expect(joined).toMatchObject({ busy: true, notice: null });
  });

  it.each(KINDS)("is read as any load reads it when that turn is already over: %s", (kind) => {
    const stored = [...EARLIER, ...SAID[kind].stored];

    expect(events(after(kind), watching(false, stored))).toMatchObject({ busy: false, notice: SAID[kind].notice });
    expect(events(after(kind), watching(false, [...stored, message({ id: "a2", role: "assistant", content: "Trả lời" })])).notice).toBeNull();
  });

  it("stays in a tab that rejoins the turn it was reading, which said it", () => {
    // Still busy: the stream broke and the same send was answered with the turn as it stands.
    const reading = events(
      act(loaded(emptyThread, EARLIER), { type: "user_sent", text: "tin mới" }, { type: "turn_started" }),
      { type: "escalated", reason: "loop", provider: "fake", model: "echo", error: "" },
    );

    const rejoined = events(reading, watching(true, [...EARLIER, SENT]));

    expect(rejoined).toMatchObject({ busy: true, notice: { kind: "escalated", text: "fake:echo", reason: "loop" } });
  });
});

describe("the notes of the person's own click, whose rule is another", () => {
  const more = [...EARLIER, SENT, ANSWER, message({ id: "u2", role: "user", content: "hỏi từ Telegram" })];

  it("stay through a load that brings more than the thread on screen had", () => {
    const stopped = act(after("fallback"), { type: "turn_started" }, { type: "turn_stopped" });
    expect(loaded(stopped, more).notice).toEqual({ kind: "stopped", text: "" });

    const handled = act(loaded(emptyThread, EARLIER), { type: "handled" });
    expect(loaded(handled, more).notice).toEqual({ kind: "handled", text: "" });
  });
});
