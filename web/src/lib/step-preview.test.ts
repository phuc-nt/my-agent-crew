import { describe, expect, it } from "vitest";
import { FAILED_KEPT_CHARS, preview, toolOutputPreview } from "./step-preview";

describe("what a step keeps of a text", () => {
  it("is the text while it is short, and its first 160 characters with a mark after", () => {
    expect(preview("x".repeat(160))).toBe("x".repeat(160));
    expect(preview(`${"x".repeat(160)}y`)).toBe(`${"x".repeat(160)}…`);
  });
});

describe("what a tool step keeps of a call that went through", () => {
  it("is the same glimpse as before", () => {
    expect(toolOutputPreview("xong", true)).toBe("xong");
    expect(toolOutputPreview("a\nb", true)).toBe("a\nb");
    expect(toolOutputPreview("x".repeat(600), true)).toBe(`${"x".repeat(160)}…`);
  });
});

describe("what a tool step keeps of a call that failed", () => {
  it("is the whole reason while it fits in 600 characters", () => {
    const reason = `${"a".repeat(161)} ${"b".repeat(438)}`;
    expect(reason).toHaveLength(600);
    expect(toolOutputPreview(reason, false)).toBe(reason);
  });

  it("is the first 200 characters, a mark, and the last 400 of a longer one", () => {
    const reason = `${"a".repeat(200)}${"m".repeat(50)}${"z".repeat(400)}`;
    const kept = toolOutputPreview(reason, false);
    expect(kept).toBe(`${"a".repeat(200)}…${"z".repeat(400)}`);
    expect(kept).toHaveLength(FAILED_KEPT_CHARS);
  });

  // A refusal says what happened and then what to do instead; the advice is its last words.
  it("keeps the advice a refusal ends with", () => {
    const advice = "Hãy gọi workspace_write trực tiếp để chủ duyệt.";
    const refusal = `Lời gọi bị từ chối. ${"Lý do dài. ".repeat(80)}${advice}`;
    expect(preview(refusal)).not.toContain(advice);
    expect(toolOutputPreview(refusal, false).endsWith(advice)).toBe(true);
  });

  it("measures the reason as the server does, with its whitespace set to single spaces", () => {
    const padded = `  dòng một\n\n   dòng hai\t${"x".repeat(580)}  `;
    expect(toolOutputPreview(padded, false)).toBe(`dòng một dòng hai ${"x".repeat(580)}`);
  });

  it("counts characters, not halves of one", () => {
    const reason = `${"😀".repeat(200)}${"m".repeat(100)}${"🙂".repeat(400)}`;
    expect(toolOutputPreview(reason, false)).toBe(`${"😀".repeat(200)}…${"🙂".repeat(400)}`);
  });
});
