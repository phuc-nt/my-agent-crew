import { describe, expect, it } from "vitest";
import { vi } from "../i18n/vi";
import { fakeRun } from "../test/fake-backend";
import { runSummaryText } from "./run-summary";

describe("run summary codes", () => {
  it("reads the halt reasons and the interrupted marker as sentences", () => {
    expect(runSummaryText(fakeRun({ status: "halted", summary: "budget" }))).toBe(vi.haltedBudget);
    expect(runSummaryText(fakeRun({ status: "halted", summary: "max_steps" }))).toBe(vi.haltedMaxSteps);
    expect(runSummaryText(fakeRun({ status: "halted", summary: "loop" }))).toBe(vi.haltedLoop);
    expect(runSummaryText(fakeRun({ status: "error", summary: "interrupted" }))).toBe(vi.runInterrupted);
  });

  it("leaves prose, and a code under a status that never writes it, as written", () => {
    expect(runSummaryText(fakeRun({ status: "done", summary: "Xong." }))).toBe("Xong.");
    expect(runSummaryText(fakeRun({ status: "done", summary: "budget" }))).toBe("budget");
    expect(runSummaryText(fakeRun({ status: "error", summary: "max_steps" }))).toBe("max_steps");
    expect(runSummaryText(fakeRun({ status: "error", summary: "rate limited" }))).toBe("rate limited");
    // Plain-object lookups would answer these with Object's own members.
    expect(runSummaryText(fakeRun({ status: "halted", summary: "constructor" }))).toBe("constructor");
    expect(runSummaryText(fakeRun({ status: "error", summary: "" }))).toBe("");
  });
});
