import { describe, expect, it } from "vitest";
import { vi } from "../i18n/vi";
import { CREATABLE_KINDS, canvasTemplate } from "./canvas-templates";

describe("what a canvas made from the web starts with", () => {
  it("lists the kinds a person can make, in the order the picker shows them", () => {
    expect(CREATABLE_KINDS).toEqual(["markdown", "code", "html", "svg", "mermaid"]);
  });

  it("starts a document and a piece of code empty", () => {
    expect(canvasTemplate("markdown")).toBe("");
    expect(canvasTemplate("code")).toBe("");
  });

  it("starts a page as the smallest page, with its body left to write", () => {
    expect(canvasTemplate("html")).toBe(
      [
        "<!doctype html>",
        '<html lang="vi">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "</head>",
        "<body>",
        "",
        "</body>",
        "</html>",
        "",
      ].join("\n"),
    );
  });

  it("starts a drawing as an svg with a view box to draw in", () => {
    expect(canvasTemplate("svg")).toBe(
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300">\n\n</svg>\n',
    );
  });

  it("starts a diagram with two boxes that already show, named in Vietnamese", () => {
    expect(canvasTemplate("mermaid")).toBe(
      `flowchart LR\n  A[${vi.canvas.templates.start}] --> B[${vi.canvas.templates.end}]\n`,
    );
    expect(canvasTemplate("mermaid")).toContain("A[Bắt đầu] --> B[Kết thúc]");
  });

  it("ends every written template in a newline, and gives the same text each time", () => {
    for (const kind of CREATABLE_KINDS) {
      const first = canvasTemplate(kind);
      expect(canvasTemplate(kind)).toBe(first);
      if (first !== "") expect(first.endsWith("\n")).toBe(true);
    }
  });

  it("stays well inside the smallest cap of any kind", () => {
    for (const kind of CREATABLE_KINDS) expect(canvasTemplate(kind).length).toBeLessThan(1024);
  });
});
