import { describe, expect, it } from "vitest";
import type { AgentEvent, ConversationDetail, ToolCall } from "../api/types";
import { emptyThread, type ThreadAction, threadReducer, type ThreadState } from "./thread-reducer";

const piece = (chunk: string, partial: Partial<Extract<AgentEvent, { type: "tool_call_delta" }>> = {}): AgentEvent => ({
  type: "tool_call_delta",
  index: 0,
  name: "artifact_create",
  chunk,
  attempt: 0,
  ...partial,
});

const answer = (tool_calls: ToolCall[], content = ""): AgentEvent => ({
  type: "assistant_message",
  message_id: `m-${tool_calls.map((call) => call.id).join("-")}`,
  content,
  tool_calls,
  provider: null,
  model: null,
  cost_usd: null,
});

const WRITE = { title: "Kế hoạch", kind: "markdown", content: "Việc một" };
const create: ToolCall = { id: "w1", name: "artifact_create", arguments: WRITE };

const act = (state: ThreadState, ...actions: ThreadAction[]) => actions.reduce(threadReducer, state);
const run = (events: AgentEvent[], from: ThreadState = { ...emptyThread, busy: true }) =>
  act(from, ...events.map((event): ThreadAction => ({ type: "event", event })));

/** A turn in which the model has written the start of one canvas. */
const writing = () => run([piece('{"title":"Kế'), piece(' hoạch","content":"Việc')]);

const detail: ConversationDetail = {
  id: "c1",
  title: "Một",
  autonomous: false,
  cost_cap_usd: 1,
  created_at: "2026-01-01T00:00:00+00:00",
  updated_at: "2026-01-01T00:00:00+00:00",
  messages: [],
  spent_usd: 0,
  unknown_cost_calls: 0,
  pending_approval: null,
} as unknown as ConversationDetail;

describe("the thread while the model writes a canvas", () => {
  it("starts from no preview at all", () => {
    expect(emptyThread.previews).toEqual([]);
    expect(emptyThread.previewSeq).toBe(0);
  });

  it("follows the pieces of the call as they arrive", () => {
    const state = writing();
    expect(state.previews).toEqual([
      {
        key: 1,
        index: 0,
        name: "artifact_create",
        text: '{"title":"Kế hoạch","content":"Việc',
        attempt: 0,
        callId: null,
        updates: 2,
      },
    ]);
    expect(state.previewSeq).toBe(1);
    expect(state.items).toEqual([]);
    expect(state.busy).toBe(true);
  });

  it("leaves a model shown as thinking shown as thinking, and one that is not as it is", () => {
    const thinking = run([{ type: "thinking" }, piece('{"ti')]);
    expect(thinking.thinking).toBe(true);
    expect(run([piece('{"ti')]).thinking).toBe(false);
    // The answer still ends the thinking, as it did.
    expect(run([answer([create])], thinking).thinking).toBe(false);
  });

  it("leaves the words of the reply that are arriving as they are", () => {
    const state = run([{ type: "text_delta", text: "Để tôi viết" }, piece('{"ti')]);
    expect(state.streaming).toBe("Để tôi viết");
  });

  it("drops the preview when the route is given up and the call starts over", () => {
    const fallback: AgentEvent = { type: "route_fallback", provider: "p", model: "m", error: "503" };
    const state = run([fallback, piece("", { name: "", attempt: 1 })], writing());
    expect(state.previews).toEqual([]);
    expect(state.previewSeq).toBe(1);
    expect(state.notice).toEqual({ kind: "fallback", text: "p:m — 503" });

    const again = run([piece('{"title":"Mới', { attempt: 1 })], state);
    expect(again.previews).toMatchObject([{ key: 2, text: '{"title":"Mới', attempt: 1, updates: 1 }]);
  });
});

describe("the thread when the step that wrote a canvas is answered", () => {
  it("gives the preview its call and keeps it through the call's result", () => {
    const answered = run([answer([create])], writing());
    expect(answered.previews).toMatchObject([{ key: 1, callId: "w1" }]);
    expect(answered.items).toMatchObject([{ kind: "tool", id: "w1", status: "running" }]);

    const result: AgentEvent = {
      type: "tool_result",
      tool_call_id: "w1",
      name: "artifact_create",
      ok: true,
      output: "[artifact 00ff00ff00ff v1]",
    };
    const done = run([{ type: "tool_call", tool_call_id: "w1", name: "artifact_create", arguments: WRITE }, result], answered);
    expect(done.previews).toBe(answered.previews);
    expect(done.items).toMatchObject([{ kind: "tool", id: "w1", status: "done" }]);
  });

  it("drops a preview whose call turned out to be another tool, with all it had read of it", () => {
    const secret = run([piece('{"path":"notes.md","content":"mật khẩu là 1234')]);
    expect(secret.previews).toHaveLength(1);

    const other: ToolCall = { id: "w1", name: "workspace_write", arguments: { path: "notes.md", content: "mật khẩu là 1234" } };
    const answered = run([answer([other])], secret);
    expect(answered.previews).toEqual([]);
    expect(answered.items).toMatchObject([{ kind: "tool", id: "w1", name: "workspace_write" }]);
  });

  it("drops the preview at the answer of the step after", () => {
    const answered = run([answer([create])], writing());
    const next = run([answer([], "Đã viết kế hoạch.")], answered);
    expect(next.previews).toEqual([]);
    expect(next.previewSeq).toBe(1);
  });

  it("leaves a thread with no preview with the very list it had", () => {
    const before = run([{ type: "text_delta", text: "Xin" }]);
    expect(run([answer([], "Xin chào")], before).previews).toBe(before.previews);
  });
});

describe("the ways a turn ends, each of which leaves no preview behind", () => {
  const approval: AgentEvent = {
    type: "approval_required",
    approval_id: "ap",
    tool_call_id: "w1",
    name: "artifact_create",
    arguments: WRITE,
    reason: "",
    expires_at: "",
  };
  const endings: [string, ThreadAction][] = [
    ["a new turn starts", { type: "turn_started" }],
    ["the stream closes", { type: "turn_finished" }],
    ["the person stops it", { type: "turn_stopped" }],
    ["the request fails", { type: "failed", message: "mất mạng" }],
    ["the turn is done", { type: "event", event: { type: "done", spent_usd: 0, unknown_cost_calls: 0 } }],
    ["the turn is halted", { type: "event", event: { type: "halted", reason: "budget", spent_usd: 1 } }],
    ["the turn errs", { type: "event", event: { type: "error", message: "hỏng" } }],
    ["the turn waits for a person", { type: "event", event: approval }],
  ];

  it.each(endings)("when %s", (_, action) => {
    for (const before of [writing(), run([answer([create])], writing())]) {
      expect(before.previews).toHaveLength(1);
      const after = act(before, action);
      expect(after.previews).toEqual([]);
      expect(after.previewSeq).toBe(1);
    }
  });

  it("starts the next turn's canvas from nothing, under a key the turn before never used", () => {
    const next = run([piece('{"content":"lượt hai')], act(writing(), { type: "turn_stopped" }, { type: "turn_started" }));
    expect(next.previews).toEqual([
      { key: 2, index: 0, name: "artifact_create", text: '{"content":"lượt hai', attempt: 0, callId: null, updates: 1 },
    ]);
  });
});

describe("the keys of previews across conversations", () => {
  it("never repeat in a tab: opening another conversation keeps the count, and so does loading it", () => {
    const opened = act(writing(), { type: "opened" });
    expect(opened).toEqual({ ...emptyThread, previewSeq: 1 });

    const loaded = act(opened, { type: "loaded", detail });
    expect(loaded.previews).toEqual([]);
    expect(loaded.previewSeq).toBe(1);

    const next = run([piece("{")], { ...loaded, busy: true });
    expect(next.previews.map((p) => p.key)).toEqual([2]);
    expect(next.previewSeq).toBe(2);
  });

  it("drops the previews of a thread loaded again", () => {
    const loaded = act(writing(), { type: "loaded", detail });
    expect(loaded.previews).toEqual([]);
    expect(loaded.previewSeq).toBe(1);
  });
});
