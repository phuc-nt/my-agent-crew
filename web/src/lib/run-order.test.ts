import { describe, expect, it } from "vitest";
import type { RunInfo } from "../api/types";
import { fakeRun } from "../test/fake-backend";
import { newestFirst } from "./run-order";

const order = (runs: RunInfo[]) => [...runs].sort(newestFirst).map((run) => run.id);

describe("newestFirst", () => {
  it("puts the run that started later first", () => {
    const early = fakeRun({ id: "early", started_at: "2026-09-19T08:00:00Z" });
    const late = fakeRun({ id: "late", started_at: "2026-09-19T08:00:01Z" });

    expect(order([early, late])).toEqual(["late", "early"]);
  });

  // Start times are whole seconds, so runs share one: a conversation's next turn can begin
  // in the second its last one ended, and jobs scheduled together start together.
  it("puts a run still going ahead of one that ended, of two that started in the same second", () => {
    const ended = fakeRun({ id: "ended" });
    const going = fakeRun({ id: "going", status: "running", finished_at: null });

    expect(order([ended, going])).toEqual(["going", "ended"]);
  });

  it("puts the one that ended later first, of two that started in the same second", () => {
    const first = fakeRun({ id: "first", finished_at: "2026-09-19T08:00:02Z" });
    const last = fakeRun({ id: "last", finished_at: "2026-09-19T08:00:09Z" });

    expect(order([first, last])).toEqual(["last", "first"]);
  });

  // A sort compares a pair either way round, and which way depends on where the pair sits
  // in the list, so each rule has to give the opposite answer when asked the other way.
  it("gives the opposite answer for a pair compared the other way round", () => {
    const going = fakeRun({ id: "going", status: "running", finished_at: null });
    const ended = fakeRun({ id: "ended" });
    const first = fakeRun({ id: "first", finished_at: "2026-09-19T08:00:02Z" });
    const last = fakeRun({ id: "last", finished_at: "2026-09-19T08:00:09Z" });
    const late = fakeRun({ id: "late", started_at: "2026-09-19T08:00:01Z" });

    for (const [ahead, behind] of [[going, ended], [last, first], [late, going]]) {
      expect(newestFirst(ahead, behind)).toBeLessThan(0);
      expect(newestFirst(behind, ahead)).toBeGreaterThan(0);
    }
  });

  it("keeps runs that share their start and their end in the order given", () => {
    const runs = ["a", "b", "c"].map((id) => fakeRun({ id }));

    expect(order(runs)).toEqual(["a", "b", "c"]);
    expect(order([...runs].reverse())).toEqual(["c", "b", "a"]);
  });
});
