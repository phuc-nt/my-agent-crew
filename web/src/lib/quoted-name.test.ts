import { describe, expect, it } from "vitest";
import { QUOTED_NAME_CHARS, quotedName, writtenName } from "./quoted-name";

/** Anything that would end a line where a sentence is drawn as it comes. */
const LINE_END = /[\n\r\v\f\u0085\u2028\u2029]/;

/** What a page makes of a text it draws, and a screen reader of a name it reads out: the
 *  white space around it gone, and each run of it one space. */
const folded = (text: string) => text.trim().replace(/\s+/g, " ");

/** A name holding one character that ends a line or draws as nothing, and how it is written
 *  between a sentence's quotes. */
const CONTROLS: Array<[string, string, string]> = [
  ["a line feed", "a\nb", '"a\\nb"'],
  ["a carriage return", "a\rb", '"a\\rb"'],
  ["a carriage return and a line feed", "a\r\nb", '"a\\r\\nb"'],
  ["a tab", "a\tb", '"a\\tb"'],
  ["a vertical tab", "a\vb", '"a\\u000bb"'],
  ["a form feed", "a\fb", '"a\\fb"'],
  ["a null", "a\u0000b", '"a\\u0000b"'],
  ["an escape", "a\u001Bb", '"a\\u001bb"'],
  ["a delete", "a\u007Fb", '"a\\u007fb"'],
  ["a next-line", "a\u0085b", '"a\\u0085b"'],
  ["a line separator", "a\u2028b", '"a\\u2028b"'],
  ["a paragraph separator", "a\u2029b", '"a\\u2029b"'],
];

describe("a name written out where it is drawn or read aloud", () => {
  it("is the name as it is when nothing in it would go unseen", () => {
    expect(writtenName("seen")).toBe("seen");
    expect(writtenName("job:brief")).toBe("job:brief");
    expect(writtenName("Bản tin sáng")).toBe("Bản tin sáng");
    expect(writtenName("")).toBe("");
  });

  it("has a quote and a backslash of its own escaped, so an escape is not read as the two characters that spell it", () => {
    expect(writtenName('a"b')).toBe('a\\"b');
    expect(writtenName("a\\b")).toBe("a\\\\b");
    expect(writtenName("a\\nb")).toBe("a\\\\nb");
    expect(writtenName("a\nb")).toBe("a\\nb");
  });

  it.each(CONTROLS)("has %s written as its escape", (_, name, quoted) => {
    expect(writtenName(name)).toBe(quoted.slice(1, -1));
    expect(writtenName(name)).not.toMatch(LINE_END);
  });

  it("leaves no control character, line separator or space of another kind as it came", () => {
    const controls = Array.from({ length: 0x20 }, (_, at) => at).concat(Array.from({ length: 0x21 }, (_, at) => 0x7f + at));
    const spaces = [0xa0, 0x1680, 0x2000, 0x2003, 0x200a, 0x2028, 0x2029, 0x202f, 0x205f, 0x2800, 0x3000];
    for (const code of [...controls, ...spaces]) {
      const char = String.fromCharCode(code);
      const written = writtenName(`a${char}b`);
      expect(written, `U+${code.toString(16)}`).not.toContain(char);
      expect(written, `U+${code.toString(16)}`).toMatch(/^a(\\[a-z]|\\u[0-9a-f]{4}|\[U\+[0-9A-F]{4}\])b$/);
    }
  });

  it.each<[string, string, string]>([
    ["one it opens with", " a", "[U+0020]a"],
    ["one it ends with", "a ", "a[U+0020]"],
    ["two between two words", "a  b", "a[U+0020][U+0020]b"],
    ["three it ends with", "a   ", "a[U+0020][U+0020][U+0020]"],
    ["two it opens with and one inside", "  a b", "[U+0020][U+0020]a b"],
    ["one and nothing else", " ", "[U+0020]"],
  ])("has the spaces a page would fold written out: %s", (_, name, written) => {
    expect(writtenName(name)).toBe(written);
  });

  it("leaves one space between two words as it is", () => {
    expect(writtenName("a b c")).toBe("a b c");
    expect(writtenName("a \nb")).toBe("a \\nb");
  });

  it.each<[string, string, string]>([
    ["a no-break space", "a\u00A0b", "a[U+00A0]b"],
    ["an ideographic space", "a\u3000b", "a[U+3000]b"],
    ["a blank braille cell", "a\u2800b", "a[U+2800]b"],
    ["a soft hyphen", "a\u00ADb", "a[U+00AD]b"],
    ["a zero-width space", "a\u200Bb", "a[U+200B]b"],
    ["a right-to-left override", "a\u202Eb", "a[U+202E]b"],
  ])("has %s written as its code point", (_, name, written) => {
    expect(writtenName(name)).toBe(written);
  });

  it.each<[string, string, string]>([
    ["a line feed for a space", "a\nb", "a b"],
    ["a carriage return before a line feed", "a\r\nb", "a\nb"],
    ["a tab for a space", "a\tb", "a b"],
    ["a next-line for a space", "a\u0085b", "a b"],
    ["a line separator for a space", "a\u2028b", "a b"],
    ["a second space", "a  b", "a b"],
    ["a space at its end", "a ", "a"],
    ["a space at its start", " a", "a"],
    ["a no-break space for a space", "a\u00A0b", "a b"],
    ["a zero-width space", "a\u200Bb", "ab"],
    ["a soft hyphen", "a\u00ADb", "ab"],
    ["a backslash and an n for a line feed", "a\\nb", "a\nb"],
  ])("reads apart from the name that differs only in %s, also once a page has folded both", (_, one, other) => {
    expect(folded(writtenName(one))).not.toBe(folded(writtenName(other)));
    // Nothing is left in it for a page to fold.
    expect(folded(writtenName(one))).toBe(writtenName(one));
    expect(folded(writtenName(other))).toBe(writtenName(other));
  });

  it("is whole however long the name is", () => {
    expect(writtenName("x".repeat(300))).toBe("x".repeat(300));
    expect(writtenName(`${"x".repeat(200)}\n`)).toBe(`${"x".repeat(200)}\\n`);
  });

  it.each(["seen", 'a"b', "a\\b", "a\nb", "a\r\nb", " a  b ", "a\u00A0b", "a\u202Eb\u200Bc", "x".repeat(80)])(
    "is what a sentence puts between its quotes (%j)",
    (name) => {
      expect(quotedName(name)).toBe(`"${writtenName(name)}"`);
    },
  );
});

describe("a name as a sentence takes it", () => {
  it("stands between double quotes, as it is", () => {
    expect(quotedName("Bản tin sáng")).toBe('"Bản tin sáng"');
    expect(quotedName("seen")).toBe('"seen"');
    expect(quotedName("")).toBe('""');
  });

  it("has a quote and a backslash of its own escaped, so the closing quote is the last one", () => {
    expect(quotedName('a"b')).toBe('"a\\"b"');
    expect(quotedName("a\\b")).toBe('"a\\\\b"');
    expect(quotedName('" của lịch "x')).toBe('"\\" của lịch \\"x"');
  });

  it.each(CONTROLS)("stays on one line with %s in it, written as its escape", (_, name, quoted) => {
    expect(quotedName(name)).toBe(quoted);
    expect(quotedName(name)).not.toMatch(LINE_END);
  });

  it("has the spaces it opens and ends with written out inside its quotes, so each one is counted", () => {
    expect(quotedName("  a  ")).toBe('"[U+0020][U+0020]a[U+0020][U+0020]"');
  });

  it("has the characters nobody would see written out", () => {
    expect(quotedName("a\u202Eb\u200Bc")).toBe('"a[U+202E]b[U+200B]c"');
  });

  it("is whole up to eighty characters, and cut there with a mark before the closing quote", () => {
    expect(QUOTED_NAME_CHARS).toBe(80);
    expect(quotedName("x".repeat(80))).toBe(`"${"x".repeat(80)}"`);
    expect(quotedName(`${"x".repeat(80)}y`)).toBe(`"${"x".repeat(80)}…"`);
    expect(quotedName("x".repeat(300))).toBe(`"${"x".repeat(80)}…"`);
  });

  it("counts characters, not halves of one", () => {
    expect(quotedName("😀".repeat(81))).toBe(`"${"😀".repeat(80)}…"`);
  });

  // Cut as stored and escaped after: the eightieth character here is a line feed.
  it("never cuts an escape in two", () => {
    expect(quotedName(`${"x".repeat(79)}\n${"y".repeat(20)}`)).toBe(`"${"x".repeat(79)}\\n…"`);
    expect(quotedName(`${"x".repeat(80)}\n`)).toBe(`"${"x".repeat(80)}…"`);
  });

  // The eightieth character is a space: the first of the two the name ends with, then one
  // that stands alone between two words.
  it("writes a space the way the whole name has it, wherever the cut falls", () => {
    expect(quotedName(`${"x".repeat(79)}  `)).toBe(`"${"x".repeat(79)}[U+0020]…"`);
    expect(quotedName(`${"x".repeat(79)} y`)).toBe(`"${"x".repeat(79)} …"`);
  });
});
