import { render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { CanvasView } from "../components/canvas/canvas-view";
import { between, find, select } from "../test/canvas-pick";
import { fromRendered, SELECTION_MAX } from "./canvas-selection";

/** `text` drawn as the canvas draws it, and the element a selection in it is read against. */
function view(text: string, kind = "markdown"): HTMLElement {
  const { container } = render(<CanvasView text={text} kind={kind} />);
  return container.querySelector(".canvas-view") as HTMLElement;
}

const outside: HTMLElement[] = [];
/** A line of text on the page, before or after whatever was drawn, that the canvas has no part in. */
function elsewhere(text: string, place: "before" | "after"): Text {
  const element = document.createElement("p");
  element.textContent = text;
  if (place === "before") document.body.prepend(element);
  else document.body.append(element);
  outside.push(element);
  return element.firstChild as Text;
}

afterEach(() => {
  for (const element of outside.splice(0)) element.remove();
  document.getSelection()?.removeAllRanges();
});

describe("the passage selected in a canvas that is being read", () => {
  it("reads a selection inside one paragraph as all the lines of that paragraph", () => {
    const source = "first line of one\nsecond line\n\nanother paragraph";
    const root = view(source);

    const picked = fromRendered(between(root, "line of one\nsecond", "second"), root, source);

    expect(picked).toEqual({ text: "first line of one\nsecond line", line_start: 1, line_end: 2, shown: 18 });
  });

  it("reads a selection across two list items as the lines of both", () => {
    const source = "- one\n- two\n- three";
    const root = view(source);
    const selection = between(root, "one", "two");

    const picked = fromRendered(selection, root, source);

    expect(picked).toMatchObject({ text: "- one\n- two", line_start: 1, line_end: 2 });
    expect(picked?.shown).toBe(selection.toString().length);
  });

  it("reads a selection from a heading down into a paragraph, the blank line between included", () => {
    const source = "# Title\n\nbody text\n\nlast";
    const root = view(source);

    expect(fromRendered(between(root, "itle", "body"), root, source)).toMatchObject({
      text: "# Title\n\nbody text",
      line_start: 1,
      line_end: 3,
    });
  });

  it("reads a selection in a code block as the whole block, fences included", () => {
    const source = "intro\n\n```js\nlet a = 1;\nlet b = 2;\n```\n\nouter";
    const root = view(source);

    const picked = fromRendered(between(root, "a = 1", "b = 2"), root, source);

    expect(picked).toMatchObject({ text: "```js\nlet a = 1;\nlet b = 2;\n```", line_start: 3, line_end: 6 });
  });

  it("reads a selection in a table cell as the row", () => {
    const source = "| A | B |\n| - | - |\n| one | two |\n| three | four |";
    const root = view(source);

    expect(fromRendered(between(root, "one", "two"), root, source)).toMatchObject({
      text: "| one | two |",
      line_start: 3,
      line_end: 3,
    });
  });

  it("counts what is seen, not the marks that draw it", () => {
    const source = "**bold** and more";
    const root = view(source);

    const picked = fromRendered(between(root, "bold", " and"), root, source);

    expect(picked).toEqual({ text: "**bold** and more", line_start: 1, line_end: 1, shown: 8 });
  });

  it("reads lines of code as the lines a selection touches, each alone", () => {
    const source = "alpha\nbeta\ngamma\ndelta\n";
    const root = view(source, "code");

    expect(fromRendered(between(root, "eta", "gam"), root, source)).toEqual({
      text: "beta\ngamma",
      line_start: 2,
      line_end: 3,
      shown: 7,
    });
    expect(fromRendered(between(root, "lph", "lph"), root, source)).toMatchObject({ text: "alpha", line_start: 1, line_end: 1 });
    expect(fromRendered(between(root, "delta", "delta"), root, source)).toMatchObject({ text: "delta", line_start: 4, line_end: 4 });
  });

  it("reads code across an empty line, and the last line of code that has no line end", () => {
    const source = "one\n\nthree";
    const root = view(source, "code");

    expect(fromRendered(between(root, "one", "three"), root, source)).toMatchObject({
      text: "one\n\nthree",
      line_start: 1,
      line_end: 3,
    });
  });

  it("is not carried off by the label of a code block's copy button between two paragraphs", () => {
    const source = "before\n\n```\ncode\n```\n\nafter";
    const root = view(source);

    expect(fromRendered(between(root, "before", "after"), root, source)).toMatchObject({
      text: source,
      line_start: 1,
      line_end: 7,
    });
  });

  it("does not take the next block for a selection that ends where it starts, as a triple click does", () => {
    const source = "first paragraph\n\nsecond paragraph";
    const root = view(source);
    const first = find(root, "first paragraph").node;
    const second = find(root, "second paragraph").node;

    expect(fromRendered(select([first, 0], [second, 0]), root, source)).toMatchObject({
      text: "first paragraph",
      line_start: 1,
      line_end: 1,
    });
    expect(fromRendered(select([first, 0], [second.parentElement as Node, 0]), root, source)).toMatchObject({
      text: "first paragraph",
      line_end: 1,
    });
  });

  it("does not count what lies after the view for a selection that ends at the start of it", () => {
    const source = "first paragraph\n\nlast paragraph";
    const root = view(source);
    const last = find(root, "last paragraph").node;
    const after = elsewhere("below the canvas", "after");

    expect(fromRendered(select([last, 0], [after, 0]), root, source)).toMatchObject({
      text: "last paragraph",
      line_start: 3,
      line_end: 3,
    });
  });

  it("reads a selection in an item holding a nested list as the lines of the item and of its nested ones", () => {
    const source = "- a\n  - b\n  - c\n- d";
    const root = view(source);

    expect(fromRendered(between(root, "a", "b"), root, source)).toMatchObject({
      text: "- a\n  - b\n  - c",
      line_start: 1,
      line_end: 3,
    });
  });

  it("reads nothing from a caret, from blanks, or from no selection at all", () => {
    const source = "a   b";
    const root = view(source);
    const text = find(root, "a   b").node;

    expect(fromRendered(select([text, 2], [text, 2]), root, source)).toBeNull();
    expect(fromRendered(select([text, 1], [text, 4]), root, source)).toBeNull();
    document.getSelection()?.removeAllRanges();
    expect(fromRendered(document.getSelection() as Selection, root, source)).toBeNull();
  });

  it("reads nothing when an end of the selection lies outside what is being read", () => {
    const source = "inside one\n\ninside two";
    const root = view(source);
    const inside = find(root, "inside two");
    const before = elsewhere("above", "before");
    const after = elsewhere("below", "after");

    expect(fromRendered(select([inside.node, 3], [after, 4]), root, source)).toBeNull();
    expect(fromRendered(select([before, 1], [inside.node, 4]), root, source)).toBeNull();
    expect(fromRendered(select([before, 1], [after, 4]), root, source)).toBeNull();
    expect(fromRendered(select([after, 1], [after, 4]), root, source)).toBeNull();
  });

  it("reads nothing from text that names no source line", () => {
    const root = document.createElement("div");
    root.innerHTML = "<p>drawn by something else</p>";
    document.body.append(root);
    outside.push(root);
    const text = find(root, "drawn").node;

    expect(fromRendered(select([text, 0], [text, 5]), root, "drawn by something else")).toBeNull();
  });

  it("clips a selection past the limit like any other", () => {
    const rows = Array.from({ length: 300 }, (_, row) => `row ${row + 1} ${"z".repeat(100)}`);
    const source = ["```", ...rows, "```"].join("\n");
    const root = view(source);

    const picked = fromRendered(between(root, "row 1 ", "row 300 "), root, source);

    expect(picked && [...picked.text].length).toBeLessThanOrEqual(SELECTION_MAX);
    expect(picked?.line_start).toBe(1);
    expect(picked?.text.startsWith("```\nrow 1 ")).toBe(true);
    expect(picked?.text.endsWith("z")).toBe(true);
    expect(picked?.line_end).toBe((picked?.text.split("\n").length ?? 0));
  });
});
