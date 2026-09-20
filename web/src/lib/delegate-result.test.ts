import { describe, expect, it } from "vitest";

import { delegateAgent, delegateTask, parseDelegateResult } from "./delegate-result";

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

  it("returns nothing when the output is an error instead of a result", () => {
    // The tool can fail before it opens a child; the card then shows the text as-is.
    expect(parseDelegateResult("Hết thời gian chờ agent con.")).toBeNull();
    expect(parseDelegateResult("")).toBeNull();
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
