import { afterEach, describe, expect, it } from "vitest";
import { between, clearPage, place } from "../test/canvas-pick";
import { fromRendered } from "./canvas-selection";

/** `html` on the page, drawn by something other than the canvas view, and the element holding it. */
function draw(html: string): HTMLElement {
  const holder = place(document.createElement("div"));
  holder.innerHTML = html;
  return holder;
}

/** What is selected from the first `text` to the last of the same, read as the panel reads it. */
const readText = (root: HTMLElement, source: string) => fromRendered(between(root, "text", "text"), root, source);

const THREE = "one\ntwo\nthree";
const TEN = Array.from({ length: 10 }, (_, row) => `line ${row + 1}`).join("\n");

afterEach(clearPage);

describe("the lines read from the blocks a selection touches", () => {
  it("leaves out a block that names lines but lies around the view, not in it", () => {
    const holder = draw('<div data-line-start="5" data-line-end="9"><div class="view"><p>text</p></div></div>');
    const root = holder.querySelector(".view") as HTMLElement;

    expect(readText(root, TEN)).toBeNull();
  });

  it("goes from the earliest first line to the latest last line of the blocks at the two ends, in either order", () => {
    const nested = '<span data-line-start="5" data-line-end="5">inner</span>';
    const innerFirst = draw(`<div data-line-start="3" data-line-end="8">${nested} outer tail</div>`);
    const outerFirst = draw(`<div data-line-start="3" data-line-end="8">outer head ${nested}</div>`);

    expect(fromRendered(between(innerFirst, "inner", "tail"), innerFirst, TEN)).toMatchObject({
      line_start: 3,
      line_end: 8,
    });
    expect(fromRendered(between(outerFirst, "head", "inner"), outerFirst, TEN)).toMatchObject({
      line_start: 3,
      line_end: 8,
    });
  });

  it("reads nothing from a block that names lines the source does not reach", () => {
    const root = draw('<p data-line-start="1" data-line-end="5">text</p>');

    expect(readText(root, THREE)).toBeNull();
    expect(readText(root, "one\ntwo\nthree\nfour\nfive")).toMatchObject({ line_start: 1, line_end: 5 });
  });

  it.each([
    ["a first line before the first", "0", "3"],
    ["a negative first line", "-1", "3"],
    ["a first line that is not whole", "1.5", "2"],
    ["a last line that is not whole", "1", "2.5"],
    ["a first line that is no number", "x", "2"],
  ])("reads nothing from a block that names %s", (_, start, end) => {
    const root = draw(`<p data-line-start="${start}" data-line-end="${end}">text</p>`);

    expect(readText(root, THREE)).toBeNull();
  });

  it("reads the lines a block names when they are whole numbers the source reaches", () => {
    const root = draw('<p data-line-start="2" data-line-end="3">text</p>');

    expect(readText(root, THREE)).toEqual({ text: "two\nthree", line_start: 2, line_end: 3, shown: 4 });
  });
});
