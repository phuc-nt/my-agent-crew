// The `steer` step across the layers that draw it: the live reducer, the row mapping and
// the progress counter. Tested together for the same reason as the progress note's own
// suite (`progress-note.test.ts`): the step is drawn once from the live event and once
// from the server's stored step, and a disagreement between the two would change the row
// under the reader the moment the run settles.
import { describe, expect, it } from "vitest";
import type { RunInfo } from "../api/types";
import { applyRunEvent } from "../state/activity-reducer";
import { noteText, runRows } from "./run-rows";
import { stepProgress, stepState } from "./run-progress";

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

describe("a steer event on a live run", () => {
  it("becomes a steer step, shortened exactly as the server shortens it", () => {
    const after = applyRunEvent(run(), { type: "steer", text: "  dừng   lại\n\nđã  ", count: 1 });
    expect(after.steps).toHaveLength(1);
    // Pinned against the same `noteText` the progress note uses, because the server
    // writes both with its one `note_text` function (`activity/steps.py`).
    expect(after.steps[0]).toMatchObject({ kind: "steer", text: noteText("dừng lại đã"), duration_ms: 0 });
  });

  it("cuts a long steer text at the same length the server cuts at", () => {
    const after = applyRunEvent(run(), { type: "steer", text: "a".repeat(500), count: 1 });
    expect(after.steps[0]).toMatchObject({ text: noteText("a".repeat(500)) });
    expect((after.steps[0] as { text: string }).text).toHaveLength(200);
  });
});

describe("a queued event on a live run", () => {
  it("never reaches the activity stream, but a run read from a stale tab is not thrown", () => {
    const before = run();
    const after = applyRunEvent(before, { type: "queued", item_id: 1, kind: "follow_up", position: 1 });
    expect(after.steps).toEqual(before.steps);
  });
});

describe("a steer step in the timeline", () => {
  const withSteer = run({ steps: [{ kind: "steer", text: "chèn vào giữa", duration_ms: 0 }] });

  it("is labelled with its own sentence and painted done", () => {
    const [row] = runRows(withSteer);
    expect(row.kind).toBe("steer");
    expect(row.label).toBe("chèn vào giữa");
    expect(stepState(withSteer.steps[0], "running")).toBe("done");
    expect(stepState(withSteer.steps[0], "done")).toBe("done");
  });

  it("never merges with the steer step beside it: two turns of steering differ even when they read alike", () => {
    const two = run({
      steps: [
        { kind: "steer", text: "chèn vào giữa", duration_ms: 0 },
        { kind: "steer", text: "chèn vào giữa", duration_ms: 0 },
      ],
    });
    expect(runRows(two)).toHaveLength(2);
  });

  it("is left out of the progress counter, like a note: it is what a person said, not a piece of work", () => {
    const mixed = run({
      status: "done",
      steps: [
        { kind: "steer", text: "chèn", duration_ms: 0 },
        { kind: "tool", name: "shell_run", tool_call_id: "t1", arguments: {}, ok: true, output: "ok", duration_ms: 10 },
      ],
    });
    expect(stepProgress(mixed)).toEqual({ done: 1, total: 1 });
  });
});
