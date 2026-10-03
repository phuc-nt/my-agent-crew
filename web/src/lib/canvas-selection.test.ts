import { describe, expect, it } from "vitest";
import { clipSelection, fromTextarea, SELECTION_MAX } from "./canvas-selection";

/** A character half of a pair is not one the server can store. */
const LONE_SURROGATE = /[\u{D800}-\u{DFFF}]/u;

/** The editor with `start` to `end` of `text` selected, read the way the panel reads it. */
function pick(text: string, start: number, end: number) {
  const field = document.createElement("textarea");
  field.value = text;
  field.setSelectionRange(start, end);
  return fromTextarea(field, text);
}

const lines = (count: number, width: number) => Array.from({ length: count }, () => "y".repeat(width));

describe("a passage clipped to what a message can take", () => {
  it("keeps a passage within the limit as it is", () => {
    expect(clipSelection("alpha\nbeta", 4, 5)).toEqual({ text: "alpha\nbeta", line_start: 4, line_end: 5 });
  });

  it("keeps a passage of exactly the limit", () => {
    const text = "x".repeat(SELECTION_MAX);
    expect(clipSelection(text, 1, 1)).toEqual({ text, line_start: 1, line_end: 1 });
  });

  it("holds to the 20000 characters the server takes, not one more and not one fewer", () => {
    expect(clipSelection("x".repeat(20000), 1, 1)?.text.length).toBe(20000);
    expect(clipSelection("x".repeat(20001), 1, 1)?.text.length).toBe(20000);
  });

  it("counts characters as the server does, a pair of code units being one", () => {
    const text = "\u{1F600}".repeat(SELECTION_MAX);
    expect(text.length).toBe(2 * SELECTION_MAX);
    expect(clipSelection(text, 1, 1)?.text).toBe(text);
  });

  it("keeps whole lines of exactly the limit in characters when a pair makes them longer in code units", () => {
    // 200 rows and 20000 characters, the last of them a pair: 20001 code units.
    const text = [...lines(199, 99), `${"y".repeat(99)}\u{1F600}`].join("\n");
    expect(text.length).toBe(20001);
    expect(clipSelection(text, 1, 200)).toEqual({ text, line_start: 1, line_end: 200 });
  });

  it("takes a passage of only blanks for nothing to ask about", () => {
    for (const blank of ["", " ", "\n\n", " \t\n  "]) expect(clipSelection(blank, 1, 3)).toBeNull();
  });

  it("cuts a longer passage at the last line end within the limit and ends it on the line before", () => {
    const rows = lines(250, 149);
    const clipped = clipSelection(rows.join("\n"), 5, 254);
    // 133 whole rows of 150 characters fit; the 134th would pass the limit.
    expect(clipped).toEqual({ text: rows.slice(0, 133).join("\n"), line_start: 5, line_end: 137 });
  });

  it("cuts at a line end that is exactly the limit's last character", () => {
    const rows = lines(250, 99);
    const clipped = clipSelection(rows.join("\n"), 5, 254);
    expect(clipped).toEqual({ text: rows.slice(0, 200).join("\n"), line_start: 5, line_end: 204 });
  });

  it("keeps a last row that ends at the limit, the line end after it being the first character left out", () => {
    const rows = [...lines(199, 99), "y".repeat(100), ...lines(50, 99)];
    const clipped = clipSelection(rows.join("\n"), 1, 250);
    expect(clipped).toEqual({ text: rows.slice(0, 200).join("\n"), line_start: 1, line_end: 200 });
  });

  it("leaves the line ends at the cut out of the passage, and the lines they would add", () => {
    const clipped = clipSelection(`A\n\n\n${"z".repeat(SELECTION_MAX)}`, 1, 4);
    expect(clipped).toEqual({ text: "A", line_start: 1, line_end: 1 });
  });

  it("cuts one line longer than the limit by characters, never through a pair", () => {
    const clipped = clipSelection(`${"a".repeat(SELECTION_MAX - 1)}\u{1F600}bbb`, 7, 7);
    expect(clipped).toEqual({ text: `${"a".repeat(SELECTION_MAX - 1)}\u{1F600}`, line_start: 7, line_end: 7 });
    expect(LONE_SURROGATE.test(clipped?.text ?? "")).toBe(false);
  });

  it("ends the cut on its first line when the first line alone passes the limit", () => {
    const clipped = clipSelection(`${"a".repeat(SELECTION_MAX + 10)}\nsecond\nthird`, 3, 5);
    expect(clipped).toEqual({ text: "a".repeat(SELECTION_MAX), line_start: 3, line_end: 3 });
  });

  it("cuts by characters, and keeps the blank line before it, when the only line end within the limit is the first character", () => {
    const clipped = clipSelection(`\n${"x".repeat(SELECTION_MAX + 5000)}`, 4, 5);
    expect(clipped).toEqual({ text: `\n${"x".repeat(SELECTION_MAX - 1)}`, line_start: 4, line_end: 5 });
  });

  it("takes a cut that leaves only blanks for nothing to ask about", () => {
    expect(clipSelection(`${" ".repeat(SELECTION_MAX + 5)}x`, 1, 1)).toBeNull();
  });
});

describe("the passage selected in the editor", () => {
  it("reads a passage from the middle of a line", () => {
    expect(pick("alpha beta\ngamma", 6, 10)).toEqual({ text: "beta", line_start: 1, line_end: 1, shown: 4 });
  });

  it("reads a passage over several lines, each end on the line it is on", () => {
    expect(pick("one\ntwo\nthree\nfour", 1, 11)).toEqual({ text: "ne\ntwo\nthr", line_start: 1, line_end: 3, shown: 10 });
  });

  it("does not count the next line for a passage that ends right after a line end", () => {
    expect(pick("one\ntwo\nthree", 4, 8)).toEqual({ text: "two", line_start: 2, line_end: 2, shown: 3 });
  });

  it("does not count the previous line for a passage that starts on a line end", () => {
    expect(pick("one\ntwo\nthree", 3, 7)).toEqual({ text: "two", line_start: 2, line_end: 2, shown: 3 });
  });

  it("drops every line end at both ends, as a line selected by a triple click comes", () => {
    expect(pick("a\n\nb\n\nc", 1, 6)).toEqual({ text: "b", line_start: 3, line_end: 3, shown: 1 });
  });

  it("keeps the indentation and the blank lines inside the passage", () => {
    expect(pick("a\n  b\n\n  c", 0, 10)).toEqual({ text: "a\n  b\n\n  c", line_start: 1, line_end: 4, shown: 10 });
  });

  it("reads nothing from a caret, from blanks, or from line ends alone", () => {
    expect(pick("one two", 3, 3)).toBeNull();
    expect(pick("one   two", 3, 6)).toBeNull();
    expect(pick("one\n\n\ntwo", 3, 6)).toBeNull();
  });

  it("clips a passage past the limit at its last line end and still says how long it was", () => {
    const rows = lines(250, 149);
    const text = rows.join("\n");
    expect(pick(text, 0, text.length)).toEqual({
      text: rows.slice(0, 133).join("\n"),
      line_start: 1,
      line_end: 133,
      shown: text.length,
    });
  });

  it("counts a passage by characters, not by code units", () => {
    expect(pick("a\u{1F600}b", 0, 4)?.shown).toBe(3);
  });
});
