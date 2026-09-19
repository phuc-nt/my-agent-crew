import { describe, expect, it } from "vitest";
import type { AgentEvent, ConversationDetail, StoredMessage } from "../api/types";
import { emptyThread, itemsFromMessages, threadReducer, type ThreadState } from "./thread-reducer";

const DENIED_TEXT = "Người dùng đã TỪ CHỐI hành động này. Không thử lại cùng hành động.";

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
    title: "t",
    created_at: "",
    updated_at: "",
    autonomous: false,
    cost_cap_usd: 1,
    skills: [],
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

  it("skips system messages and assistant messages with no content or calls", () => {
    expect(itemsFromMessages([message({ role: "system", content: "x" }), message({ role: "assistant" })])).toEqual([]);
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
          },
        }),
      },
    );
    expect(state.spentUsd).toBe(0.2);
    expect(state.unknownCostCalls).toBe(1);
    expect(state.pending).toEqual({ approvalId: "ap1", toolCallId: "tc", name: "write_file", arguments: { path: "x" } });
    expect(state.items[0]).toMatchObject({ kind: "tool", status: "awaiting" });
    expect(state.busy).toBe(false);
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
      { type: "approval_required", approval_id: "ap", tool_call_id: "tc", name: "write_file", arguments: {} },
    ]);
    expect(paused.busy).toBe(false);
    expect(paused.pending?.approvalId).toBe("ap");
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

  it("user_sent appends locally and turn_started clears the previous notice", () => {
    const withNotice = threadReducer(emptyThread, { type: "failed", message: "x" });
    const sent = threadReducer(withNotice, { type: "user_sent", text: "hello" });
    expect(sent.items).toEqual([{ kind: "user", id: "local-0", text: "hello" }]);
    expect(sent.notice).toBeNull();
    expect(threadReducer(sent, { type: "turn_started" })).toMatchObject({ busy: true, streaming: null });
  });
});
