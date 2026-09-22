import { describe, expect, it } from "vitest";
import type { RunInfo, RunStatus, RunStep } from "../api/types";
import {
  activeStep,
  isSettled,
  measuredDurationMs,
  runElapsedMs,
  stepProgress,
  stepState,
} from "./run-progress";

function toolStep(ok: boolean | null, name = "shell_run", duration: number | null = 40): RunStep {
  return { kind: "tool", name, tool_call_id: `c-${name}-${ok}`, arguments: {}, ok, output: null, duration_ms: duration };
}

function modelStep(tool_calls: string[] = [], duration: number | null = 100): RunStep {
  return {
    kind: "model",
    chars: 120,
    provider: "openrouter",
    model: "m",
    cost_usd: 0.001,
    tool_calls,
    preview: "…",
    duration_ms: duration,
  };
}

function run(status: RunStatus, steps: RunStep[], overrides: Partial<RunInfo> = {}): RunInfo {
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
    ...overrides,
  };
}

describe("isSettled", () => {
  it("treats done, halted and error as final", () => {
    expect(isSettled("done")).toBe(true);
    expect(isSettled("halted")).toBe(true);
    expect(isSettled("error")).toBe(true);
  });

  it("treats running and awaiting_approval as still open", () => {
    expect(isSettled("running")).toBe(false);
    expect(isSettled("awaiting_approval")).toBe(false);
  });
});

describe("stepState", () => {
  it("reads an unclosed tool step as running only while the run is", () => {
    expect(stepState(toolStep(null), "running")).toBe("running");
    expect(stepState(toolStep(null), "awaiting_approval")).toBe("running");
  });

  it("calls an unclosed tool step stalled once the run has settled", () => {
    // The failure this guards: a run that errored out mid-tool would otherwise
    // keep a spinner turning on that row for as long as the page is open.
    expect(stepState(toolStep(null), "error")).toBe("stalled");
    expect(stepState(toolStep(null), "halted")).toBe("stalled");
    expect(stepState(toolStep(null), "done")).toBe("stalled");
  });

  it("keeps a closed tool step's own outcome regardless of the run", () => {
    expect(stepState(toolStep(true), "error")).toBe("done");
    expect(stepState(toolStep(false), "done")).toBe("failed");
  });

  it("treats a model step as done and a fallback as failed", () => {
    expect(stepState(modelStep(), "running")).toBe("done");
    expect(
      stepState({ kind: "fallback", provider: "p", model: "m", error: "e", duration_ms: 5 }, "running"),
    ).toBe("failed");
  });
});

describe("activeStep", () => {
  it("names the newest still-open step", () => {
    const later = toolStep(null, "web_fetch");
    const active = activeStep(run("running", [modelStep(), toolStep(true), later]));
    expect(active).toBe(later);
  });

  it("has nothing to name once the run settles", () => {
    expect(activeStep(run("done", [modelStep(), toolStep(null)]))).toBeNull();
  });
});

describe("stepProgress", () => {
  it("counts every non-running step as finished", () => {
    expect(stepProgress(run("running", [modelStep(), toolStep(true), toolStep(null)]))).toEqual({
      done: 2,
      total: 3,
    });
  });

  it("reports a settled run as fully accounted for even with an unclosed step", () => {
    expect(stepProgress(run("error", [modelStep(), toolStep(null)]))).toEqual({ done: 2, total: 2 });
  });
});

describe("runElapsedMs", () => {
  const now = Date.parse("2026-09-22T07:00:30+00:00");

  it("measures against now while the run is open", () => {
    expect(runElapsedMs(run("running", []), now)).toBe(30_000);
  });

  it("freezes at finished_at once the run closes", () => {
    const settled = run("done", [], { finished_at: "2026-09-22T07:00:12+00:00" });
    expect(runElapsedMs(settled, now)).toBe(12_000);
    // A later `now` must not move a finished run's duration.
    expect(runElapsedMs(settled, now + 60_000)).toBe(12_000);
  });

  // Status and finished_at are stamped by different things, so a run recorded
  // outside the hub arrives settled with no timestamp. Measuring that against
  // the current clock reported hours for a run that took a moment.
  it("falls back to what the steps took when a settled run has no finish time", () => {
    const settled = run("done", [modelStep([], 100), toolStep(true, "x", 40)]);
    expect(runElapsedMs(settled, now)).toBe(140);
    expect(runElapsedMs(settled, now + 60_000)).toBe(140);
  });

  it("returns zero rather than NaN on an unparseable timestamp", () => {
    expect(runElapsedMs(run("running", [], { started_at: "nonsense" }), now)).toBe(0);
  });

  it("never reports negative time when the clocks disagree", () => {
    expect(runElapsedMs(run("running", []), Date.parse("2026-09-22T06:59:00+00:00"))).toBe(0);
  });
});

describe("measuredDurationMs", () => {
  it("adds up only the steps that recorded a duration", () => {
    expect(measuredDurationMs(run("done", [modelStep([], 100), toolStep(true, "x", null), toolStep(true, "y", 40)]))).toBe(
      140,
    );
  });
});
