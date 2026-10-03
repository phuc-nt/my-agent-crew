import { describe, expect, it } from "vitest";
import { CAPS, MESSAGE_MAX, SMALLEST_CAP, capOf, fits, utf8Bytes } from "./canvas-caps";

const KB = 1024;
const MB = 1024 * KB;

describe("the size one version of a canvas may have", () => {
  it.each([
    ["markdown", 512 * KB],
    ["code", 512 * KB],
    ["html", 4 * MB],
    ["svg", 2 * MB],
    ["mermaid", 512 * KB],
    ["image", 2 * MB],
  ])("holds a %s canvas to %i bytes", (kind, cap) => {
    expect(capOf(kind)).toBe(cap);
    expect(CAPS[kind]).toBe(cap);
  });

  it("holds a kind it does not know, or none, to the smallest cap", () => {
    const unknown = ["video", "", "HTML", null, undefined, "constructor", "toString", "__proto__", "hasOwnProperty"];
    for (const kind of unknown) expect(capOf(kind), String(kind)).toBe(512 * KB);
    expect(SMALLEST_CAP).toBe(512 * KB);
  });

  it("takes a chat message to be at most 20000 characters", () => {
    expect(MESSAGE_MAX).toBe(20000);
  });
});

describe("counting a text in UTF-8 bytes", () => {
  it.each([
    ["", 0],
    ["abc", 3],
    ["é", 2],
    ["ệ", 3],
    ["😀", 4],
    ["Ghi chú", 8],
  ])("counts %j as %i", (text, bytes) => {
    expect(utf8Bytes(text)).toBe(bytes);
  });
});

describe("whether a text fits the cap of its kind", () => {
  it.each([
    ["markdown", 512 * KB],
    ["html", 4 * MB],
    ["svg", 2 * MB],
    ["mermaid", 512 * KB],
  ])("takes %s text of exactly %i bytes and refuses one byte more", (kind, cap) => {
    expect(fits("x".repeat(cap), kind)).toBe(true);
    expect(fits("x".repeat(cap + 1), kind)).toBe(false);
  });

  it("counts bytes, not characters, on both sides of the cap", () => {
    // Two bytes each: the characters alone would let twice as much through.
    expect(fits("é".repeat(256 * KB), "markdown")).toBe(true);
    expect(fits("é".repeat(256 * KB + 1), "markdown")).toBe(false);
    // Three bytes each: a length of a third of the cap is the limit the quick check cannot pass.
    expect(fits("ệ".repeat(Math.floor((512 * KB) / 3)), "markdown")).toBe(true);
    expect(fits("ệ".repeat(Math.floor((512 * KB) / 3) + 1), "markdown")).toBe(false);
  });

  it("holds each kind to its own cap", () => {
    const text = "x".repeat(1.5 * MB);

    expect(fits(text, "html")).toBe(true);
    expect(fits(text, "svg")).toBe(true);
    expect(fits(text, "markdown")).toBe(false);
    expect(fits(text, "mermaid")).toBe(false);
    expect(fits(text, "code")).toBe(false);
  });

  it("holds a canvas whose kind is not known yet to the smallest cap", () => {
    expect(fits("x".repeat(512 * KB), undefined)).toBe(true);
    expect(fits("x".repeat(512 * KB + 1), undefined)).toBe(false);
    expect(fits("x".repeat(512 * KB + 1), "video")).toBe(false);
  });
});
