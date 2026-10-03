import { describe, expect, it } from "vitest";
import { cleanTitle } from "./canvas-title";

describe("a canvas title as the server keeps it", () => {
  it("keeps one line of visible text as it is", () => {
    expect(cleanTitle("Ghi chú cuộc họp")).toBe("Ghi chú cuộc họp");
  });

  it("makes line breaks and runs of spaces single spaces", () => {
    expect(cleanTitle("  Hai\ndòng \r\n\t và   thêm  ")).toBe("Hai dòng và thêm");
  });

  it("counts as spaces every character Python's isspace does", () => {
    const spaces = [
      0x0b, 0x0c, 0x1c, 0x1d, 0x1e, 0x1f, 0x85, 0xa0, 0x1680, 0x2000, 0x2005, 0x200a, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000,
    ];
    for (const code of spaces) {
      expect(cleanTitle(`a${String.fromCodePoint(code)}b`), code.toString(16)).toBe("a b");
    }
  });

  it("drops the byte order mark rather than spacing it, as the server does", () => {
    expect(cleanTitle("a\u{FEFF}b")).toBe("ab");
  });

  it("drops control and format characters, bidi overrides and zero-width spaces among them", () => {
    expect(cleanTitle("a\u{202E}b\u{200B}c\u{0}d\u{7}e\u{2066}f")).toBe("abcdef");
  });

  it("keeps the joiners that hold an emoji sequence together", () => {
    expect(cleanTitle("a\u{200D}b\u{200C}c")).toBe("a\u{200D}b\u{200C}c");
    expect(cleanTitle("\u{1F468}\u{200D}\u{1F469}\u{200D}\u{1F467}")).toBe("\u{1F468}\u{200D}\u{1F469}\u{200D}\u{1F467}");
  });

  it("composes what a keyboard may have sent decomposed", () => {
    expect(cleanTitle("Vie\u{302}\u{323}t")).toBe("Vi\u{1EC7}t");
  });

  it("asks for a title when nothing visible is left", () => {
    const problem = { problem: "a canvas needs a title" };
    expect(cleanTitle("")).toEqual(problem);
    expect(cleanTitle(" \n\t ")).toEqual(problem);
    expect(cleanTitle("\u{200B}\u{202E}")).toEqual(problem);
  });

  it("allows 200 characters and says how many it saw above that", () => {
    expect(cleanTitle("x".repeat(200))).toBe("x".repeat(200));
    expect(cleanTitle("x".repeat(201))).toEqual({ problem: "a title of 201 characters is over 200" });
  });

  it("counts a character once however many UTF-16 units it takes", () => {
    const face = "\u{1F600}";
    expect(cleanTitle(face.repeat(200))).toBe(face.repeat(200));
    expect(cleanTitle(face.repeat(201))).toEqual({ problem: "a title of 201 characters is over 200" });
  });

  it("counts after cleaning, not before", () => {
    expect(cleanTitle(`${"x".repeat(200)}\u{200B} \n`)).toBe("x".repeat(200));
    expect(cleanTitle("e\u{301}".repeat(200))).toBe("\u{E9}".repeat(200));
  });
});
