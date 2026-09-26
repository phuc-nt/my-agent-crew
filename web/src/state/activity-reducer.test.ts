import { describe, expect, it } from "vitest";
import type { RunInfo } from "../api/types";
import {
  activityReducer,
  applyRunEvent,
  emptyActivity,
  liveRuns,
  needsAttention,
  parentConversationId,
  runGroups,
  runsForConversation,
  sortedRuns,
} from "./activity-reducer";

function run(overrides: Partial<RunInfo> = {}): RunInfo {
  return {
    id: "r1",
    agent_id: "default",
    conversation_id: "c1",
    source: "chat",
    title: "t",
    status: "running",
    started_at: "2026-09-19T08:00:00Z",
    finished_at: null,
    spent_usd: 0,
    unknown_cost_calls: 0,
    summary: "",
    steps: [],
    ...overrides,
  };
}

describe("applyRunEvent", () => {
  it("turns assistant messages into model steps and tracks honest cost", () => {
    const a = applyRunEvent(run(), {
      type: "assistant_message",
      message_id: "m1",
      content: "x".repeat(200),
      tool_calls: [{ id: "tc", name: "read_file", arguments: {} }],
      provider: "openrouter",
      model: "deepseek",
      cost_usd: 0.002,
    });
    expect(a.steps).toHaveLength(1);
    expect(a.steps[0]).toMatchObject({ kind: "model", chars: 200, model: "deepseek", tool_calls: ["read_file"] });
    expect((a.steps[0] as { preview: string }).preview.endsWith("…")).toBe(true);
    expect(a.spent_usd).toBeCloseTo(0.002);
    // A local model reports no price: counted as unknown, never as free.
    const b = applyRunEvent(a, {
      type: "assistant_message",
      message_id: "m2",
      content: "",
      tool_calls: [],
      provider: "ollama",
      model: "llama3",
      cost_usd: null,
    });
    expect(b.unknown_cost_calls).toBe(1);
    expect(b.summary).toBe(a.summary);
  });

  it("completes the model step a snapshot caught mid-call instead of adding a second", () => {
    // A tab that connects while the model is answering gets the run with that call open:
    // no answer, no price, no tool calls yet. The answer closes that step, as on the server.
    const midCall = run({ steps: [{ kind: "model", chars: 5, first_token_ms: 300, duration_ms: null }] });
    const next = applyRunEvent(midCall, {
      type: "assistant_message",
      message_id: "m1",
      content: "xin chào",
      tool_calls: [],
      provider: "openrouter",
      model: "deepseek",
      cost_usd: 0.001,
    });
    expect(next.steps).toHaveLength(1);
    expect(next.steps[0]).toMatchObject({ kind: "model", chars: 5, first_token_ms: 300, model: "deepseek", cost_usd: 0.001 });
    expect(next.spent_usd).toBeCloseTo(0.001);
  });

  it("adds no model step for a child's answer handed on whole, as the server does not", () => {
    const relayed = applyRunEvent(run({ summary: "delegate" }), {
      type: "assistant_message",
      message_id: "m2",
      content: "Có 3 tệp.",
      tool_calls: [],
      provider: null,
      model: null,
      cost_usd: 0,
    });
    expect(relayed.steps).toHaveLength(0);
    expect(relayed.unknown_cost_calls).toBe(0);
    expect(relayed.summary).toBe("delegate");
  });

  it("opens a tool step on tool_call and closes it with the matching tool_result", () => {
    const opened = applyRunEvent(run(), { type: "tool_call", tool_call_id: "tc", name: "shell_run", arguments: { command: "ls" } });
    expect(opened.steps[0]).toMatchObject({ kind: "tool", name: "shell_run", ok: null, output: null });
    const closed = applyRunEvent(opened, { type: "tool_result", tool_call_id: "tc", name: "shell_run", ok: false, output: "boom" });
    expect(closed.steps[0]).toMatchObject({ kind: "tool", ok: false, output: "boom" });
    const stray = applyRunEvent(closed, { type: "tool_result", tool_call_id: "zz", name: "x", ok: true, output: "" });
    expect(stray.steps).toHaveLength(1);
  });

  it("copies final totals from done/halted and messages from errors and approvals", () => {
    expect(applyRunEvent(run(), { type: "done", spent_usd: 0.5, unknown_cost_calls: 2 })).toMatchObject({ spent_usd: 0.5, unknown_cost_calls: 2 });
    expect(applyRunEvent(run(), { type: "halted", reason: "budget", spent_usd: 1 })).toMatchObject({ summary: "budget", spent_usd: 1 });
    expect(applyRunEvent(run(), { type: "error", message: "kaput" }).summary).toBe("kaput");
    expect(applyRunEvent(run(), { type: "approval_required", approval_id: "a", tool_call_id: "t", name: "write_file", arguments: {}, reason: "", expires_at: "" }).summary).toBe("write_file");
    expect(applyRunEvent(run(), { type: "approval_required", approval_id: "a", tool_call_id: "t", name: "shell_run", arguments: {}, reason: "khớp mẫu cần duyệt: `sudo `", expires_at: "" }).summary).toBe("shell_run (khớp mẫu cần duyệt: `sudo `)");
    expect(applyRunEvent(run(), { type: "text_delta", text: "…" }).steps).toEqual([]);
    expect(applyRunEvent(run(), { type: "model_call", stage: "sent" }).steps).toEqual([]);
  });

  it("records a route fallback as its own step so a failing route is visible", () => {
    const fell = applyRunEvent(run(), { type: "route_fallback", provider: "openrouter", model: "glm", error: "HTTP 429 from glm" });
    expect(fell.steps).toEqual([{ kind: "fallback", provider: "openrouter", model: "glm", error: "HTTP 429 from glm", duration_ms: null }]);
    expect(fell.spent_usd).toBe(run().spent_usd);
  });
});

describe("activityReducer", () => {
  it("merges snapshot, run and event payloads and keeps live runs over stale recent ones", () => {
    let state = activityReducer(emptyActivity, { type: "payload", payload: { type: "snapshot", runs: [run()] } });
    expect(state.connected).toBe(true);
    state = activityReducer(state, {
      type: "payload",
      payload: { type: "event", run_id: "r1", agent_id: "default", conversation_id: "c1", status: "running", event: { type: "tool_call", tool_call_id: "tc", name: "read_file", arguments: {} } },
    });
    expect(state.runs.r1.steps).toHaveLength(1);
    // The REST list still reports the old snapshot: it must not clobber the live run.
    state = activityReducer(state, { type: "recent", runs: [run({ steps: [] }), run({ id: "r0", status: "done", started_at: "2026-09-19T07:00:00Z" })] });
    expect(state.runs.r1.steps).toHaveLength(1);
    expect(state.runs.r0.status).toBe("done");
    // Unknown run ids in events are ignored rather than invented.
    const same = activityReducer(state, {
      type: "payload",
      payload: { type: "event", run_id: "nope", agent_id: "default", conversation_id: null, status: "running", event: { type: "text_delta", text: "" } },
    });
    expect(same).toBe(state);
    state = activityReducer(state, { type: "payload", payload: { type: "run", run: run({ status: "done", finished_at: "2026-09-19T08:01:00Z" }) } });
    expect(state.runs.r1.status).toBe("done");
    state = activityReducer(state, { type: "connection", connected: false });
    expect(state.connected).toBe(false);
  });

  it("derives sorted, live, per-conversation and attention views", () => {
    const state = activityReducer(emptyActivity, {
      type: "recent",
      runs: [
        run({ id: "old", status: "done", started_at: "2026-09-19T06:00:00Z" }),
        run({ id: "wait", status: "awaiting_approval", conversation_id: "c2", started_at: "2026-09-19T09:00:00Z" }),
        run({ id: "bad", status: "error", started_at: "2026-09-19T08:30:00Z" }),
        run({ id: "live", status: "running", conversation_id: null, source: "job:coach/brief", started_at: "2026-09-19T10:00:00Z" }),
      ],
    });
    expect(sortedRuns(state).map((r) => r.id)).toEqual(["live", "wait", "bad", "old"]);
    expect(liveRuns(state).map((r) => r.id)).toEqual(["live", "wait"]);
    expect(runsForConversation(state, "c1").map((r) => r.id)).toEqual(["bad", "old"]);
    expect(needsAttention(state).map((r) => r.id)).toEqual(["wait", "bad"]);
  });
});

describe("runGroups", () => {
  it("tucks a delegated run under the run that asked for it", () => {
    const parent = run({ id: "p", conversation_id: "c-parent", started_at: "2026-09-19T08:00:00Z" });
    const child = run({
      id: "k",
      conversation_id: "c-child",
      source: "delegate:c-parent",
      started_at: "2026-09-19T08:01:00Z",
    });

    const groups = runGroups([child, parent]);

    expect(groups).toHaveLength(1);
    expect(groups[0].run.id).toBe("p");
    expect(groups[0].children.map((c) => c.id)).toEqual(["k"]);
  });

  it("keeps a child visible when its parent run is not in view", () => {
    const orphan = run({ id: "k", conversation_id: "c-child", source: "delegate:gone" });

    const groups = runGroups([orphan]);

    expect(groups.map((g) => g.run.id)).toEqual(["k"]);
    expect(groups[0].children).toEqual([]);
  });

  it("nests only one level, because a child cannot delegate on", () => {
    const parent = run({ id: "p", conversation_id: "c-parent" });
    const a = run({ id: "a", conversation_id: "c-a", source: "delegate:c-parent" });
    const b = run({ id: "b", conversation_id: "c-b", source: "delegate:c-parent" });

    const groups = runGroups([parent, a, b]);

    expect(groups).toHaveLength(1);
    expect(groups[0].children.map((c) => c.id).sort()).toEqual(["a", "b"]);
  });

  it("reads the parent conversation out of the run source", () => {
    expect(parentConversationId(run({ source: "delegate:c-9" }))).toBe("c-9");
    expect(parentConversationId(run({ source: "chat" }))).toBeNull();
    expect(parentConversationId(run({ source: "job:coach/brief" }))).toBeNull();
  });
});
