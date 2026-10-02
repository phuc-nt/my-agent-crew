import { describe, expect, it } from "vitest";
import { hasHiddenChars, showHiddenChars } from "./hidden-chars";

describe("characters that change how text reads without being seen", () => {
  it("shows a right-to-left override as a visible mark", () => {
    expect(showHiddenChars("a‮b")).toBe("a[U+202E]b");
    expect(hasHiddenChars("a‮b")).toBe(true);
  });

  it("shows every bidi control and zero-width character", () => {
    const hidden = [
      0x061c, 0x200b, 0x200c, 0x200d, 0x200e, 0x200f, 0x202a, 0x202b, 0x202c, 0x202d, 0x202e, 0x2060, 0x2066, 0x2067,
      0x2068, 0x2069, 0xfeff,
    ];
    for (const code of hidden) {
      const mark = `[U+${code.toString(16).toUpperCase().padStart(4, "0")}]`;
      expect(showHiddenChars(`x${String.fromCodePoint(code)}y`)).toBe(`x${mark}y`);
      expect(hasHiddenChars(String.fromCodePoint(code))).toBe(true);
    }
  });

  it("leaves ordinary text, Vietnamese and whitespace as they are", () => {
    const text = "Tiếng Việt có dấu\n\tthụt lề  và khoảng trắng → ✓";
    expect(showHiddenChars(text)).toBe(text);
    expect(hasHiddenChars(text)).toBe(false);
  });

  it("answers the same on every call", () => {
    expect(hasHiddenChars("a​b")).toBe(true);
    expect(hasHiddenChars("a​b")).toBe(true);
    expect(hasHiddenChars("ab")).toBe(false);
  });
});
