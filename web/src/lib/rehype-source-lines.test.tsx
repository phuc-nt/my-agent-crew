import { render } from "@testing-library/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { describe, expect, it } from "vitest";
import { type HastNode, markSourceLines, rehypeSourceLines } from "./rehype-source-lines";

/** The source lines each marked element says it came from, in document order: "p 1-2". */
function marks(source: string): string[] {
  const { container } = render(
    <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSourceLines]}>
      {source}
    </ReactMarkdown>,
  );
  return [...container.querySelectorAll("[data-line-start]")].map(
    (el) => `${el.tagName.toLowerCase()} ${el.getAttribute("data-line-start")}-${el.getAttribute("data-line-end")}`,
  );
}

describe("the source lines a rendered block came from", () => {
  it("marks each paragraph with the first and last line it was written on", () => {
    expect(marks("one\ntwo\n\nthree")).toEqual(["p 1-2", "p 4-4"]);
  });

  it("marks headings of every style, a setext heading over its two lines", () => {
    expect(marks("# Title\n\ntext\n\n### Sub\n\nSetext\n=====")).toEqual(["h1 1-1", "p 3-3", "h3 5-5", "h1 7-8"]);
  });

  it("marks a list item with its own lines, the item holding a nested list with the nested lines too", () => {
    expect(marks("- a\n  - b\n  - c\n- d")).toEqual(["li 1-3", "li 2-2", "li 3-3", "li 4-4"]);
    expect(marks("1. x\n2. y\n   more of y")).toEqual(["li 1-1", "li 2-3"]);
  });

  it("marks a table and each of its rows, not the separator row or the cells", () => {
    expect(marks("| A | B |\n| - | - |\n| 1 | 2 |\n| 3 | 4 |")).toEqual(["table 1-4", "tr 1-1", "tr 3-3", "tr 4-4"]);
  });

  it("marks a code block and the code in it with the lines of the block, fences included", () => {
    expect(marks("```ts\nconst a = 1;\nconst b = 2;\n```\n\nafter")).toEqual(["pre 1-4", "code 1-4", "p 6-6"]);
  });

  it("leaves code inside a sentence unmarked, so a selection in it is read from its paragraph", () => {
    expect(marks("use `x` here")).toEqual(["p 1-1"]);
  });

  it("marks a quote and the paragraph inside it", () => {
    expect(marks("> one\n> two\n\nafter")).toEqual(["blockquote 1-2", "p 1-2", "p 4-4"]);
  });

  it("marks nothing else: emphasis, links, lists as a whole, rules and cells are left as they are", () => {
    expect(marks("**bold** and *it* and [x](https://e.test)\n\n- a\n\n---")).toEqual(["p 1-1", "li 3-3"]);
  });

  it("takes an element without a position as one with no lines to name, and keeps its properties", () => {
    const element = (tagName: string, extra: Partial<HastNode> = {}): HastNode => ({
      type: "element",
      tagName,
      properties: { className: ["keep"] },
      children: [],
      ...extra,
    });
    const placed = element("p", { position: { start: { line: 3 }, end: { line: 4 } } });
    const loose = element("li");
    const code = element("code", { position: { start: { line: 9 }, end: { line: 9 } } });
    const pre = element("pre", { position: { start: { line: 7 }, end: { line: 10 } }, children: [code] });

    markSourceLines({ type: "root", children: [placed, loose, pre] });

    expect(placed.properties).toEqual({ className: ["keep"], dataLineStart: 3, dataLineEnd: 4 });
    expect(loose.properties).toEqual({ className: ["keep"] });
    expect(pre.properties).toEqual({ className: ["keep"], dataLineStart: 7, dataLineEnd: 10 });
    // The code of a block takes the block's lines, not the position it carries itself.
    expect(code.properties).toEqual({ className: ["keep"], dataLineStart: 7, dataLineEnd: 10 });
  });

  it("is not forged by markup in the text, which shows as text", () => {
    expect(marks('<p data-line-start="9" data-line-end="9">x</p>\n\ntext')).toEqual(["p 3-3"]);
  });
});
