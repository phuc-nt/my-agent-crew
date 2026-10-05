import { describe, expect, it } from "vitest";
import type { AgentEvent, Approval, ConversationDetail, ToolCall } from "../api/types";
import { emptyThread, type ThreadAction, threadReducer, type ThreadState } from "./thread-reducer";

const event = (e: AgentEvent): ThreadAction => ({ type: "event", event: e });
const act = (state: ThreadState, ...actions: ThreadAction[]) => actions.reduce(threadReducer, state);

const piece = (chunk: string, attempt = 0): ThreadAction =>
  event({ type: "tool_call_delta", index: 0, name: "artifact_create", chunk, attempt });

const answer = (tool_calls: ToolCall[], content = ""): ThreadAction =>
  event({ type: "assistant_message", message_id: "m1", content, tool_calls, provider: null, model: null, cost_usd: null });

/** A call that waits for the person's word before it runs. */
const write: ToolCall = { id: "f1", name: "write_file", arguments: { path: "ghi.md", content: "x" } };
const asks = (approval_id = "ap1"): ThreadAction =>
  event({ type: "approval_required", approval_id, tool_call_id: "f1", name: "write_file", arguments: write.arguments, reason: "", expires_at: "" });
const written = event({ type: "tool_result", tool_call_id: "f1", name: "write_file", ok: true, output: "Đã ghi." });

const PUT_AWAY: ThreadAction = { type: "previews_muted" };
const done = event({ type: "done", spent_usd: 0, unknown_cost_calls: 0 });
const halted = event({ type: "halted", reason: "budget", spent_usd: 1 });
const erred = event({ type: "error", message: "hỏng" });

/** A turn in which the model has written the start of a canvas. */
const writing = () => act({ ...emptyThread, busy: true }, piece('{"title":"Kế'), piece(' hoạch","content":"Việc'));
/** The same turn once the person has put that canvas away. */
const putAway = () => act(writing(), PUT_AWAY);
/** That turn stopped for the person's word on a later call, its stream closed behind the request. */
const paused = () => act(putAway(), answer([write]), asks(), { type: "turn_finished" });

const request = (id: string): Approval =>
  ({ id, conversation_id: "c1", tool_call_id: "f1", tool_name: "write_file", arguments: write.arguments, status: "pending" }) as Approval;

const loaded = (pending_approval: Approval | null): ThreadAction => ({
  type: "loaded",
  detail: { id: "c1", messages: [], spent_usd: 0, unknown_cost_calls: 0, pending_approval } as unknown as ConversationDetail,
});

describe("a canvas being written that the person put away", () => {
  it("is put away by nobody to begin with", () => {
    expect(emptyThread.previewsMuted).toBe(false);
    expect(writing().previewsMuted).toBe(false);
  });

  it("is remembered by the thread, which changes nothing else: the canvas keeps its card", () => {
    const before = writing();
    const after = act(before, PUT_AWAY);

    expect(after).toEqual({ ...before, previewsMuted: true });
    expect(after.previews).toBe(before.previews);
  });

  it("stays put away through whatever the turn goes on to say", () => {
    const create: ToolCall = { id: "w1", name: "artifact_create", arguments: {} };
    const steps: ThreadAction[] = [
      piece(" một"),
      event({ type: "route_fallback", provider: "p", model: "m", error: "503" }),
      piece("", 1),
      piece('{"title":"Bản mới"', 1),
      event({ type: "thinking" }),
      event({ type: "text_delta", text: "Để tôi viết" }),
      answer([create], "Để tôi viết"),
      event({ type: "tool_call", tool_call_id: "w1", name: "artifact_create", arguments: {} }),
      event({ type: "tool_result", tool_call_id: "w1", name: "artifact_create", ok: true, output: "[artifact 00ff00ff00ff v1]" }),
      event({ type: "steer", text: "nhanh lên", count: 0 }),
      { type: "queued", item: { id: 1, kind: "follow_up", text: "rồi sao nữa" } },
      { type: "queue_cleared" },
      { type: "queue_failed", message: "đầy" },
      { type: "settled" },
      { type: "handled" },
      { type: "elsewhere" },
    ];
    let state = putAway();
    for (const step of steps) {
      state = act(state, step);
      expect(state.previewsMuted, step.type === "event" ? step.event.type : step.type).toBe(true);
    }
  });
});

describe("a canvas put away in a turn that then waits for the person", () => {
  it("is still put away while the request waits, with the stream closed behind it", () => {
    const asked = act(putAway(), answer([write]), asks());
    expect(asked).toMatchObject({ previewsMuted: true, busy: false, previews: [] });
    expect(asked.pending?.approvalId).toBe("ap1");

    expect(paused()).toMatchObject({ previewsMuted: true, busy: false });
    expect(paused().pending?.approvalId).toBe("ap1");
  });

  it("is still put away when the person has answered and the turn goes on to write another canvas", () => {
    const resumed = act(paused(), { type: "turn_started" });
    expect(resumed).toMatchObject({ previewsMuted: true, busy: true });

    const next = act(resumed, written, piece('{"title":"Danh sách'), piece(' chợ","content":"Rau'));
    expect(next.pending).toBeNull();
    expect(next.previews).toHaveLength(1);
    expect(next.previewsMuted).toBe(true);
  });

  it("is still put away when their answer could not be sent, and the request waits as before", () => {
    const failed = act(paused(), { type: "turn_started" }, { type: "failed", message: "mất mạng" });
    expect(failed.pending?.approvalId).toBe("ap1");
    expect(failed.previewsMuted).toBe(true);
  });

  it("is still put away after a load that finds the same request waiting", () => {
    const again = act(paused(), loaded(request("ap1")));
    expect(again.pending?.approvalId).toBe("ap1");
    expect(again.previewsMuted).toBe(true);
  });

  it("is forgotten at a load that finds the request closed: that turn went on or ended somewhere else", () => {
    expect(act(paused(), loaded(null)).previewsMuted).toBe(false);
  });

  it("is forgotten at a load that finds another request waiting: that one is another turn's", () => {
    const other = act(paused(), loaded(request("ap2")));
    expect(other.pending?.approvalId).toBe("ap2");
    expect(other.previewsMuted).toBe(false);
  });

  it("is forgotten when the person stops the turn instead of answering", () => {
    expect(act(paused(), { type: "turn_stopped" })).toMatchObject({ previewsMuted: false, pending: null });
  });

  it.each([
    ["done", done],
    ["halted", halted],
    ["in error", erred],
  ])("is forgotten when the server says the turn is %s, whatever the page still shows as waiting", (_, end) => {
    expect(paused().pending).not.toBeNull();
    expect(act(paused(), { type: "turn_started" }, end).previewsMuted).toBe(false);
  });
});

describe("the ends of a turn, each of which forgets what the person put away in it", () => {
  const endings: [string, ThreadAction][] = [
    ["the turn is done", done],
    ["the turn is halted", halted],
    ["the turn errs", erred],
    ["the stream closes with no request waiting", { type: "turn_finished" }],
    ["the person stops it", { type: "turn_stopped" }],
    ["the request fails with no request waiting", { type: "failed", message: "mất mạng" }],
    ["another conversation is opened", { type: "opened" }],
    ["the thread is loaded again", loaded(null)],
  ];

  it.each(endings)("when %s", (_, action) => {
    const before = putAway();
    expect(before.pending).toBeNull();
    expect(act(before, action).previewsMuted).toBe(false);
  });

  it("when another conversation is opened while this one waits for the person", () => {
    expect(act(paused(), { type: "opened" })).toEqual({ ...emptyThread, previewSeq: 1 });
  });

  it("and the turn that starts next owes it nothing, even one put away when no turn was going", () => {
    const idle: ThreadState = { ...emptyThread, previewsMuted: true };
    const next = act(idle, { type: "user_sent", text: "viết tiếp" }, { type: "turn_started" });
    expect(next).toMatchObject({ busy: true, previewsMuted: false });
  });
});
