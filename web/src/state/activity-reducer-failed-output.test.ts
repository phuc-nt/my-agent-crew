import { describe, expect, it } from "vitest";
import type { RunInfo } from "../api/types";
import { fakeRun } from "../test/fake-backend";
import { applyRunEvent } from "./activity-reducer";

const ADVICE = "Hãy gọi workspace_write trực tiếp để chủ duyệt.";

/** A run with one call open, then closed by `output`. */
function closed(ok: boolean, output: string): RunInfo {
  const live = fakeRun({ status: "running", finished_at: null, steps: [] });
  const opened = applyRunEvent(live, { type: "tool_call", tool_call_id: "tc", name: "tool_script", arguments: {} });
  return applyRunEvent(opened, { type: "tool_result", tool_call_id: "tc", name: "tool_script", ok, output });
}

describe("a tool step heard live", () => {
  // The step is drawn from the event until the run settles and the server's copy takes its
  // place. Cut at a glimpse here, a refusal lost the advice it ends with for as long as the
  // run went on.
  it("keeps the whole reason of a call that failed", () => {
    const refusal = `Lời gọi bị từ chối: script chỉ đọc không được ghi. ${"Chi tiết. ".repeat(30)}${ADVICE}`;
    expect(refusal.length).toBeGreaterThan(160);
    expect(refusal.length).toBeLessThanOrEqual(600);

    expect(closed(false, refusal).steps[0]).toMatchObject({ kind: "tool", ok: false, output: refusal });
  });

  it("keeps the start and the end of a reason too long to keep whole", () => {
    const refusal = `${"a".repeat(200)}${"giữa ".repeat(100)}${"z".repeat(400 - ADVICE.length)}${ADVICE}`;

    const [step] = closed(false, refusal).steps;

    expect(step).toMatchObject({ output: `${"a".repeat(200)}…${"z".repeat(400 - ADVICE.length)}${ADVICE}` });
  });

  it("keeps a glimpse of a call that went through, as before", () => {
    expect(closed(true, "x".repeat(600)).steps[0]).toMatchObject({ ok: true, output: `${"x".repeat(160)}…` });
  });
});
