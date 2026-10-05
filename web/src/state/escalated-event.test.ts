import { describe, expect, it } from "vitest";
import type { AgentEvent, RunInfo, RunStep } from "../api/types";
import { applyRunEvent } from "./activity-reducer";
import { emptyThread, threadReducer, type ThreadState } from "./thread-reducer";

const LOOP: AgentEvent = { type: "escalated", reason: "loop", provider: "openrouter", model: "big", error: "" };
const DOWN: AgentEvent = {
  type: "escalated",
  reason: "error",
  provider: "openrouter",
  model: "big",
  error: "every route failed — openrouter:flash: HTTP 502",
};
const FELL: AgentEvent = { type: "route_fallback", provider: "openrouter", model: "flash", error: "HTTP 502" };

function thread(events: AgentEvent[], from: ThreadState = { ...emptyThread, busy: true }): ThreadState {
  return events.reduce((s, event) => threadReducer(s, { type: "event", event }), from);
}

function run(steps: RunStep[] = []): RunInfo {
  return {
    id: "r1",
    agent_id: "default",
    conversation_id: "c1",
    source: "chat",
    title: "t",
    status: "running",
    started_at: "2026-10-06T08:00:00Z",
    finished_at: null,
    spent_usd: 0,
    unknown_cost_calls: 0,
    summary: "",
    steps,
  };
}

const OPEN: RunStep = { kind: "model", chars: 0, first_token_ms: null, duration_ms: null };
const ANSWERED: RunStep = {
  kind: "model",
  chars: 0,
  provider: "openrouter",
  model: "flash",
  cost_usd: 0.001,
  tool_calls: ["count_up"],
  preview: "",
  duration_ms: 900,
};

describe("a turn that moved to its escalation route, in the thread", () => {
  it("says which route the rest of it runs on and why, and keeps going", () => {
    const moved = thread([LOOP]);

    expect(moved.notice).toEqual({ kind: "escalated", text: "openrouter:big", reason: "loop" });
    expect(moved.busy).toBe(true);
  });

  it("takes the place of the notice the routes that failed left", () => {
    const moved = thread([FELL, DOWN]);

    expect(moved.notice).toEqual({ kind: "escalated", text: "openrouter:big", reason: "error" });
    expect(moved.busy).toBe(true);
    expect(moved.items).toEqual([]);
  });

  it("is still said once the turn ends well", () => {
    const done = thread([LOOP, { type: "done", spent_usd: 0.02, unknown_cost_calls: 0 }]);

    expect(done.busy).toBe(false);
    expect(done.notice).toMatchObject({ kind: "escalated", reason: "loop" });
  });
});

describe("a turn that moved to its escalation route, in its run", () => {
  it("is a step of its own after the call that was refused for repeating itself", () => {
    const moved = applyRunEvent(run([ANSWERED]), LOOP);

    expect(moved.steps).toEqual([
      ANSWERED,
      { kind: "escalation", reason: "loop", provider: "openrouter", model: "big", duration_ms: null },
    ]);
    expect(moved.spent_usd).toBe(0);
  });

  it("takes the place of the call no route answered, so the next answer is a call of its own", () => {
    const fell = applyRunEvent(run([OPEN]), FELL);
    const moved = applyRunEvent(fell, DOWN);

    expect(moved.steps.map((s) => s.kind)).toEqual(["fallback", "escalation"]);
    expect(moved.steps[1]).toEqual({
      kind: "escalation",
      reason: "error",
      provider: "openrouter",
      model: "big",
      error: "every route failed — openrouter:flash: HTTP 502",
      duration_ms: null,
    });

    const answered = applyRunEvent(moved, {
      type: "assistant_message",
      message_id: "m1",
      content: "xong",
      tool_calls: [],
      provider: "openrouter",
      model: "big",
      cost_usd: 0.01,
    });
    expect(answered.steps.map((s) => s.kind)).toEqual(["fallback", "escalation", "model"]);
    expect(answered.steps[2]).toMatchObject({ model: "big", chars: 4 });
  });

  it("stands alone when no call was caught open", () => {
    const moved = applyRunEvent(run(), DOWN);

    expect(moved.steps.map((s) => s.kind)).toEqual(["escalation"]);
  });

  it("keeps what the routes said short, as the server stores it", () => {
    const long = applyRunEvent(run(), { ...DOWN, error: "x".repeat(400) });
    const step = long.steps[0];

    expect(step.kind === "escalation" && step.error).toBe(`${"x".repeat(160)}…`);
  });
});
