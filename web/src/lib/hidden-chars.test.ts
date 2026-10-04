import { describe, expect, it } from "vitest";
import { hasHiddenChars, showHiddenChars, showPathChars } from "./hidden-chars";

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

const marked = (code: number) => `[U+${code.toString(16).toUpperCase().padStart(4, "0")}]`;

describe("what a path holds that nobody would see", () => {
  // Every one of these the server keeps in a path as it was sent: none is a control or a format
  // character, the only ones `check_path` refuses.
  const STORED = [
    // Spaces that are not the ordinary one.
    0x00a0, 0x1680, 0x2000, 0x2005, 0x200a, 0x202f, 0x205f, 0x3000,
    // Letters and marks that draw as nothing: fillers, a joiner, selectors.
    0x034f, 0x115f, 0x1160, 0x17b4, 0x180b, 0x3164, 0xffa0, 0xfe00, 0xfe0f, 0xe0100,
    // A blank drawn by a symbol, and code points that mean whatever a font says they do.
    0x2800, 0xe000, 0xf8ff, 0xf0000, 0x10fffd,
  ];

  it.each(STORED)("writes a character the server stores and no one sees as its code point: %i", (code) => {
    const char = String.fromCodePoint(code);

    expect(showPathChars(`notes/pl${char}an.md`)).toBe(`notes/pl${marked(code)}an.md`);
    expect(showPathChars(char)).toBe(marked(code));
  });

  it("writes each space a part of the path opens or ends with, and leaves the spaces inside a name", () => {
    expect(showPathChars("notes/plan.md ")).toBe("notes/plan.md[U+0020]");
    expect(showPathChars(" notes/plan.md")).toBe("[U+0020]notes/plan.md");
    expect(showPathChars("ghi chú /tuần 1/ thực đơn.md")).toBe("ghi chú[U+0020]/tuần 1/[U+0020]thực đơn.md");
    expect(showPathChars("a/  b  /c")).toBe("a/[U+0020][U+0020]b[U+0020][U+0020]/c");
    expect(showPathChars("a/ /b")).toBe("a/[U+0020]/b");
    expect(showPathChars(" ")).toBe("[U+0020]");
  });

  it("writes a space at an end beside a character no one sees, both of them", () => {
    expect(showPathChars("plan.md \u{3164}")).toBe("plan.md [U+3164]");
    expect(showPathChars("plan.md\u{00A0} ")).toBe("plan.md[U+00A0][U+0020]");
  });

  it("still writes the characters that hide or reorder text", () => {
    expect(showPathChars("a\u{202E}b/c\u{200B}d\u{FEFF}.md")).toBe("a[U+202E]b/c[U+200B]d[U+FEFF].md");
  });

  it("leaves a name anyone can read as it is, whatever script or form it is written in", () => {
    const names = [
      "ghi chú/tuần 1/thực đơn.md",
      "ghi chú/thực đơn.md".normalize("NFD"),
      "한글 문서.md".normalize("NFD"),
      "日本語/メモ.txt",
      "😀 vui.md",
      ".env.example",
      "a..b/c--d__e (1).md",
      "",
      "/",
      "a//b/",
    ];
    for (const name of names) expect(showPathChars(name), name).toBe(name);
  });
});
