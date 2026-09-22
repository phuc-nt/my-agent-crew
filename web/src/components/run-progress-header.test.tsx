import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RunInfo, RunStatus, RunStep } from "../api/types";
import { vi } from "../i18n/vi";
import { RunProgressHeader } from "./run-progress-header";

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

function run(steps: RunStep[], status: RunStatus, overrides: Partial<RunInfo> = {}): RunInfo {
  return {
    id: "r1",
    agent_id: "master",
    conversation_id: "c1",
    source: "chat",
    title: "t",
    status,
    started_at: new Date(Date.now() - 4000).toISOString(),
    finished_at: null,
    spent_usd: 0,
    unknown_cost_calls: 0,
    summary: "",
    steps,
    ...overrides,
  };
}

describe("RunProgressHeader", () => {
  it("names the tool currently blocking the turn", () => {
    render(<RunProgressHeader run={run([toolStep(), toolStep({ name: "shell_run", ok: null })], "running")} />);
    expect(screen.getByTestId("run-progress")).toHaveTextContent(vi.runDoing("shell_run"));
  });

  it("says it is waiting on the person rather than claiming to be thinking", () => {
    // Before this, a run stopped on a question reported "Đang suy nghĩ" and kept the
    // shimmer running, so the person sat watching for work that only their answer starts.
    const asked: RunStep = { kind: "question", question: "Dời hạn?", duration_ms: null };
    const { container } = render(<RunProgressHeader run={run([toolStep(), asked], "awaiting_approval")} />);
    expect(screen.getByTestId("run-progress")).toHaveTextContent(vi.runWaitingAnswer);
    expect(container.querySelector(".run-progress.live")).toBeNull();
  });

  it("keeps a waiting question out of the finished count", () => {
    const asked: RunStep = { kind: "question", question: "Dời hạn?", duration_ms: null };
    render(<RunProgressHeader run={run([toolStep(), asked], "awaiting_approval")} />);
    expect(screen.getByTestId("run-progress")).toHaveTextContent(vi.runStepCount(1, 2));
  });

  it("falls back to thinking when no step is open yet", () => {
    render(<RunProgressHeader run={run([], "running")} />);
    expect(screen.getByTestId("run-progress")).toHaveTextContent(vi.runThinking);
  });

  it("counts finished steps out of the steps that exist", () => {
    render(<RunProgressHeader run={run([toolStep(), toolStep({ ok: null })], "running")} />);
    expect(screen.getByTestId("run-progress")).toHaveTextContent(vi.runStepCount(1, 2));
  });

  it("stops claiming work is under way once the run has settled", () => {
    // The step is still open in the data, but the run is not: the header must
    // not keep announcing a tool that stopped when the run died.
    const { container } = render(<RunProgressHeader run={run([toolStep({ ok: null })], "error")} />);
    expect(screen.getByTestId("run-progress")).toHaveTextContent(vi.runEndedError);
    expect(container.querySelector(".run-progress.live")).toBeNull();
  });

  // A finished run has no "right now". Borrowing the live wording made every
  // run in the list read as still thinking, which looks like a hang.
  it("says how the run ended rather than what it is doing, once it is over", () => {
    render(<RunProgressHeader run={run([toolStep()], "done")} />);
    expect(screen.getByTestId("run-progress")).toHaveTextContent(vi.runEndedDone);
    expect(screen.getByTestId("run-progress")).not.toHaveTextContent(vi.runThinking);
  });

  it("names a halt as a halt, not as a failure", () => {
    render(<RunProgressHeader run={run([toolStep()], "halted")} />);
    expect(screen.getByTestId("run-progress")).toHaveTextContent(vi.runEndedHalted);
  });

  it("reports the bar as complete when every step is accounted for", () => {
    render(<RunProgressHeader run={run([toolStep(), toolStep()], "done")} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
  });

  it("holds the bar at zero for a run that has produced no steps", () => {
    render(<RunProgressHeader run={run([], "running")} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  });

  it("freezes the clock at finished_at instead of counting past it", () => {
    const settled = run([toolStep()], "done", {
      started_at: "2026-09-22T07:00:00+00:00",
      finished_at: "2026-09-22T07:00:02+00:00",
    });
    render(<RunProgressHeader run={settled} />);
    expect(screen.getByTestId("run-progress")).toHaveTextContent(vi.runElapsed(2000));
  });
});
