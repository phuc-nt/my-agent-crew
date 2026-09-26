import { describe, expect, it } from "vitest";
import type { RunInfo, RunStatus, RunStep } from "../api/types";
import { runRows } from "./run-rows";
import { vi } from "../i18n/vi";

function toolStep(overrides: Partial<Extract<RunStep, { kind: "tool" }>> = {}): RunStep {
  return {
    kind: "tool",
    name: "web_search",
    tool_call_id: "c1",
    arguments: {},
    ok: true,
    output: null,
    duration_ms: 50,
    ...overrides,
  };
}

function run(steps: RunStep[], status: RunStatus = "done"): RunInfo {
  return {
    id: "r1",
    agent_id: "master",
    conversation_id: "c1",
    source: "chat",
    title: "t",
    status,
    started_at: "2026-09-22T07:00:00+00:00",
    finished_at: null,
    spent_usd: 0,
    unknown_cost_calls: 0,
    summary: "",
    steps,
  };
}

describe("runRows", () => {
  it("collapses a retry loop into one row carrying the count", () => {
    const rows = runRows(run([toolStep(), toolStep(), toolStep()]));
    expect(rows).toHaveLength(1);
    expect(rows[0].repeat).toBe(3);
    expect(rows[0].label).toBe("web_search");
  });

  it("totals the duration of every step a collapsed row covers", () => {
    const rows = runRows(run([toolStep({ duration_ms: 50 }), toolStep({ duration_ms: 70 })]));
    expect(rows[0].durationMs).toBe(120);
  });

  it("leaves a collapsed row unmeasured only when no step measured anything", () => {
    const none = runRows(run([toolStep({ duration_ms: null }), toolStep({ duration_ms: null })]));
    expect(none[0].durationMs).toBeNull();
    const some = runRows(run([toolStep({ duration_ms: null }), toolStep({ duration_ms: 70 })]));
    expect(some[0].durationMs).toBe(70);
  });

  it("never collapses a running row, since that is the row being watched", () => {
    const rows = runRows(run([toolStep({ ok: null }), toolStep({ ok: null })], "running"));
    expect(rows).toHaveLength(2);
    expect(rows.every((r) => r.state === "running")).toBe(true);
  });

  it("never collapses a row that carries its own output", () => {
    const rows = runRows(run([toolStep({ output: "one" }), toolStep({ output: "two" })]));
    expect(rows).toHaveLength(2);
  });

  it("keeps rows apart when they differ in name or in outcome", () => {
    const byName = runRows(run([toolStep({ name: "a" }), toolStep({ name: "b" })]));
    expect(byName).toHaveLength(2);
    const byOutcome = runRows(run([toolStep({ ok: true }), toolStep({ ok: false })]));
    expect(byOutcome).toHaveLength(2);
  });

  it("only collapses steps that are adjacent", () => {
    const rows = runRows(run([toolStep({ name: "a" }), toolStep({ name: "b" }), toolStep({ name: "a" })]));
    expect(rows.map((r) => r.label)).toEqual(["a", "b", "a"]);
    expect(rows.every((r) => r.repeat === 1)).toBe(true);
  });

  it("reads a handoff to another agent as its own kind", () => {
    const rows = runRows(run([toolStep({ name: "delegate" })]));
    expect(rows[0].kind).toBe("delegate");
  });

  it("labels a model row by its model and a fallback by provider and model", () => {
    const rows = runRows(
      run([
        {
          kind: "model",
          chars: 10,
          provider: "openrouter",
          model: "sonnet",
          cost_usd: 0.1,
          tool_calls: [],
          preview: "",
          duration_ms: 20,
        },
        { kind: "fallback", provider: "groq", model: "llama", error: "429", duration_ms: 5 },
      ]),
    );
    expect(rows.map((r) => [r.kind, r.label, r.state])).toEqual([
      ["model", "sonnet", "done"],
      ["fallback", "groq:llama", "failed"],
    ]);
  });

  // Runs stored before a route fallback moved the open model step kept it stranded ahead
  // of the route that answered. On a finished run that row is not thinking.
  it("names an unanswered model row by its role once the run has settled", () => {
    const open: RunStep = { kind: "model", chars: 0, first_token_ms: null, duration_ms: null };
    expect(runRows(run([open], "done")).map((r) => [r.label, r.state])).toEqual([
      [vi.stepModelUnnamed, "stalled"],
    ]);
    expect(runRows(run([open], "running"))[0].label).toBe(vi.runThinking);
  });

  it("labels a question row with what was asked, not with the tool that asked it", () => {
    // "ask_user" on the row would tell the reader a tool is waiting. What waits is a
    // sentence only they can finish, so the sentence is the label.
    const rows = runRows(
      run([{ kind: "question", question: "Dời hạn sang thứ sáu?", duration_ms: null }], "awaiting_approval"),
    );
    expect(rows.map((r) => [r.kind, r.label, r.state])).toEqual([
      ["question", "Dời hạn sang thứ sáu?", "waiting"],
    ]);
  });

  it("never folds two questions together however alike they read", () => {
    // Each question is its own ask with its own answer; a "×2" would hide one of them.
    const asked: RunStep = { kind: "question", question: "Tiếp chứ?", duration_ms: null };
    const rows = runRows(run([asked, { ...asked }], "awaiting_approval"));
    expect(rows).toHaveLength(2);
  });

  it("gives each row a key that stays put as later rows collapse", () => {
    const rows = runRows(run([toolStep({ name: "a" }), toolStep({ name: "b" }), toolStep({ name: "b" })]));
    expect(rows.map((r) => r.key)).toEqual([0, 1]);
  });
});
