import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RunStep } from "../api/types";
import { vi } from "../i18n/vi";
import { stepState } from "../lib/run-progress";
import { runRows } from "../lib/run-rows";
import { fakeRun } from "../test/fake-backend";
import { RunCard } from "./run-timeline";

const FELL: RunStep = { kind: "fallback", provider: "openrouter", model: "flash", error: "HTTP 502", duration_ms: 2000 };
const FOR_ERROR: RunStep = {
  kind: "escalation",
  reason: "error",
  provider: "openrouter",
  model: "big",
  error: "every route failed — openrouter:flash: HTTP 502",
  duration_ms: 1500,
};
const FOR_LOOP: RunStep = { kind: "escalation", reason: "loop", provider: "openrouter", model: "big", duration_ms: 0 };

describe("a move to the escalation route as a row", () => {
  it("is named by the route moved to and went through whatever the run did next", () => {
    const rows = runRows(fakeRun({ status: "error", steps: [FELL, FOR_ERROR] }));

    expect(rows.map((r) => [r.kind, r.label, r.state])).toEqual([
      ["fallback", "openrouter:flash", "failed"],
      ["escalation", "openrouter:big", "done"],
    ]);
    expect(stepState(FOR_LOOP, "running")).toBe("done");
    expect(stepState(FOR_LOOP, "halted")).toBe("done");
  });

  it("is never folded into another: each says why it was made", () => {
    const rows = runRows(fakeRun({ steps: [FOR_LOOP, FOR_LOOP] }));

    expect(rows).toHaveLength(2);
    expect(rows.every((r) => r.repeat === 1)).toBe(true);
  });
});

describe("a move to the escalation route on the timeline", () => {
  it("says the route, that it is an escalation, why, and what the routes said", () => {
    render(<RunCard run={fakeRun({ steps: [FELL, FOR_ERROR] })} agentName="HLV" expanded />);
    const [, moved] = screen.getAllByTestId("run-step");

    expect(moved).toHaveClass("step", "escalation", "done");
    expect(moved).toHaveTextContent("openrouter:big");
    expect(moved).toHaveTextContent(vi.stepEscalation);
    expect(moved).toHaveTextContent(vi.stepEscalationReason.error);
    expect(moved).toHaveTextContent("every route failed — openrouter:flash: HTTP 502");
    // As long as the call that never answered.
    expect(moved).toHaveTextContent(vi.stepDuration(1500));
    expect(moved).not.toHaveTextContent(vi.stepFallback);
  });

  it("says a loop in its own words, with no error and no time it did not take", () => {
    render(<RunCard run={fakeRun({ steps: [FOR_LOOP] })} agentName="HLV" expanded />);
    const moved = screen.getByTestId("run-step");

    expect(moved).toHaveTextContent(vi.stepEscalationReason.loop);
    expect(moved).not.toHaveTextContent(vi.stepEscalationReason.error);
    expect(moved).not.toHaveTextContent("—");
    expect(moved.querySelector(".step-time")).toBeNull();
    // Its outcome is carried by the word, and still spoken.
    expect(moved.querySelector(".step-state")).toBeNull();
    expect(moved.querySelector(".sr-only")).toHaveTextContent(vi.toolDone);
  });

  it("shows no time for a move a live run has not closed yet", () => {
    const live: RunStep = { ...FOR_ERROR, duration_ms: null };
    render(<RunCard run={fakeRun({ status: "running", finished_at: null, steps: [live] })} agentName="HLV" expanded />);

    expect(screen.getByTestId("run-step").querySelector(".step-time")).toBeNull();
  });
});
