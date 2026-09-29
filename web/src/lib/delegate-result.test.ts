import { describe, expect, it } from "vitest";

import {
  type DelegateResult,
  delegateAgent,
  delegateTask,
  delegateTone,
  parseDelegateResult,
} from "./delegate-result";

const HEADER = "conversation=c-9 status=done spent=$0.0421 steps=7";

describe("parseDelegateResult", () => {
  it("splits the header from the child's reply", () => {
    const parsed = parseDelegateResult(`${HEADER}\nĐã sửa xong hai tệp.\nCòn một câu hỏi.`);

    expect(parsed).toEqual({
      conversationId: "c-9",
      status: "done",
      spentUsd: 0.0421,
      steps: 7,
      reply: "Đã sửa xong hai tệp.\nCòn một câu hỏi.",
    });
  });

  it("reads a header with no reply after it", () => {
    expect(parseDelegateResult(HEADER)?.reply).toBe("");
  });

  it("reads what the task came to, and why, from the second line", () => {
    const output = `${HEADER}\noutcome=blocked reason=workspace_write denied\nKhông ghi được.`;

    expect(parseDelegateResult(output)).toEqual({
      conversationId: "c-9",
      status: "done",
      spentUsd: 0.0421,
      steps: 7,
      outcome: "blocked",
      outcomeReason: "workspace_write denied",
      reply: "Không ghi được.",
    });
  });

  it("reads an outcome with no reason, and one with no reply after it", () => {
    const done = parseDelegateResult(`${HEADER}\noutcome=done\nĐã xong.`);
    const timedOut = parseDelegateResult(`${HEADER}\noutcome=failed reason=timeout`);

    expect(done?.outcome).toBe("done");
    expect(done).not.toHaveProperty("outcomeReason");
    expect(done?.reply).toBe("Đã xong.");
    expect(timedOut?.outcomeReason).toBe("timeout");
    expect(timedOut?.reply).toBe("");
  });

  it("leaves the outcome out for a result written before there was one", () => {
    // Older results in the history go straight from the header to the reply.
    const parsed = parseDelegateResult(`${HEADER}\nĐã sửa.\noutcome=done`);

    expect(parsed).not.toHaveProperty("outcome");
    expect(parsed?.reply).toBe("Đã sửa.\noutcome=done");
  });

  it("returns nothing when the output is an error instead of a result", () => {
    // The tool can fail before it opens a child; the card then shows the text as-is.
    expect(parseDelegateResult("Hết thời gian chờ agent con.")).toBeNull();
    expect(parseDelegateResult("")).toBeNull();
  });
});

describe("delegateTone", () => {
  const base: DelegateResult = {
    conversationId: "c",
    status: "done",
    spentUsd: 0,
    steps: 1,
    reply: "",
  };

  it("goes by the outcome when there is one", () => {
    expect(delegateTone({ ...base, outcome: "done" })).toBe("ok");
    expect(delegateTone({ ...base, outcome: "blocked" })).toBe("warn");
    expect(delegateTone({ ...base, outcome: "done_with_concerns" })).toBe("warn");
    expect(delegateTone({ ...base, outcome: "failed" })).toBe("danger");
  });

  it("goes by how the run ended for a result that has no outcome", () => {
    expect(delegateTone(base)).toBe("ok");
    expect(delegateTone({ ...base, status: "halted" })).toBe("danger");
  });
});

describe("delegateTask", () => {
  it("cuts a long task and leaves a short one alone", () => {
    expect(delegateTask({ task: "  dọn mã  " })).toBe("dọn mã");
    expect(delegateTask({ task: "x".repeat(200) })).toHaveLength(141);
    expect(delegateTask({ task: "x".repeat(200) }).endsWith("…")).toBe(true);
  });

  it("survives arguments that are not what we expect", () => {
    expect(delegateTask({})).toBe("");
    expect(delegateTask({ task: 7 })).toBe("");
    expect(delegateAgent({ agent: "coder" })).toBe("coder");
    expect(delegateAgent({})).toBe("");
  });
});
