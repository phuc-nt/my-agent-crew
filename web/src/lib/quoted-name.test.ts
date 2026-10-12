import { describe, expect, it } from "vitest";
import { QUOTED_NAME_CHARS, quotedName } from "./quoted-name";

/** Anything that would end a line where a sentence is drawn as it comes. */
const LINE_END = /[\n\r\v\f\u0085\u2028\u2029]/;

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

  it.each<[string, string, string]>([
    ["a line feed", "a\nb", '"a\\nb"'],
    ["a carriage return", "a\rb", '"a\\rb"'],
    ["a tab", "a\tb", '"a\\tb"'],
    ["a vertical tab", "a\vb", '"a\\u000bb"'],
    ["a form feed", "a\fb", '"a\\fb"'],
    ["a null", "a\u0000b", '"a\\u0000b"'],
    ["an escape", "a\u001Bb", '"a\\u001bb"'],
    ["a delete", "a\u007Fb", '"a\\u007fb"'],
    ["a next-line", "a\u0085b", '"a\\u0085b"'],
    ["a line separator", "a\u2028b", '"a\\u2028b"'],
    ["a paragraph separator", "a\u2029b", '"a\\u2029b"'],
  ])("stays on one line with %s in it, written as its escape", (_, name, quoted) => {
    expect(quotedName(name)).toBe(quoted);
    expect(quotedName(name)).not.toMatch(LINE_END);
  });

  it("keeps the spaces it opens and ends with, inside its quotes", () => {
    expect(quotedName("  a  ")).toBe('"  a  "');
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
});
