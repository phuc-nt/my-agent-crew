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

// Python's `str.split()` and JavaScript's `\s` do not agree on what whitespace is. The server
// sets a reason's whitespace to single spaces with the first, so the web goes by it too.
describe("what counts as whitespace in a failed call's reason", () => {
  const char = (code: number) => String.fromCodePoint(code);
  const named = (code: number) => `U+${code.toString(16).toUpperCase().padStart(4, "0")}`;

  it.each([0x1c, 0x1d, 0x1e, 0x1f, 0x85].map((code) => [named(code), char(code)]))(
    "%s is whitespace, which it is for the server and not for JavaScript",
    (_name, space) => {
      expect(toolOutputPreview(`${space}một${space}${space}hai${space}`, false)).toBe("một hai");
    },
  );

  it("U+FEFF is part of a word, which it is for the server and not for JavaScript", () => {
    const mark = char(0xfeff);
    const reason = `${mark}một${mark}${mark}hai${mark}`;
    expect(toolOutputPreview(reason, false)).toBe(reason);
  });

  it("is every character the server's split parts a text at, and no other", () => {
    // The whole of Python's `str.isspace`. Nothing past U+3000 is in it, and a character
    // past U+FFFF is two halves here, each of them looked at below.
    const ranges = [[0x09, 0x0d], [0x1c, 0x20], [0x85, 0x85], [0xa0, 0xa0], [0x1680, 0x1680], [0x2000, 0x200a], [0x2028, 0x2029], [0x202f, 0x202f], [0x205f, 0x205f], [0x3000, 0x3000]];
    const forServer = (code: number) => ranges.some(([from, to]) => code >= from && code <= to);
    const wrong: string[] = [];
    for (let code = 0; code <= 0xffff; code += 1) {
      const whole = `a${char(code)}b`;
      if (toolOutputPreview(whole, false) !== (forServer(code) ? "a b" : whole)) wrong.push(named(code));
    }
    expect(wrong).toEqual([]);
  });

  it("leaves whole a reason that fits only once the server's whitespace is one space", () => {
    // 598, two separators and one more: 600 as the server counts it, 601 by JavaScript's rule.
    const reason = `${"x".repeat(598)}${char(0x1f)}${char(0x85)}y`;
    expect(toolOutputPreview(reason, false)).toBe(`${"x".repeat(598)} y`);
  });

  it("cuts a reason that would fit only if U+FEFF were whitespace", () => {
    // 601 as the server counts it; JavaScript's rule made the two marks one space, and 600.
    const mark = char(0xfeff);
    const reason = `${"x".repeat(598)}${mark}${mark}y`;
    expect(toolOutputPreview(reason, false)).toBe(`${"x".repeat(200)}…${"x".repeat(397)}${mark}${mark}y`);
  });
});
