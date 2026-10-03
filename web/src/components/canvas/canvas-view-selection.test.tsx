import { render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi as vitest } from "vitest";
import { announceSelection, clearPage, elsewhere, find, select } from "../../test/canvas-pick";
import { CanvasView } from "./canvas-view";

const SOURCE = "inside one\n\ninside two";

afterEach(clearPage);

function setup() {
  const onSelection = vitest.fn();
  const { container } = render(<CanvasView text={SOURCE} kind="markdown" onSelection={onSelection} />);
  const root = container.querySelector(".canvas-view") as HTMLElement;
  return { onSelection, one: find(root, "inside one").node, two: find(root, "inside two").node };
}

/** What the page was told went wrong while `action` ran: jsdom reports what a listener throws as an error event. */
function raised(action: () => void): unknown[] {
  const errors: unknown[] = [];
  const note = (event: ErrorEvent) => {
    event.preventDefault();
    errors.push(event.error);
  };
  window.addEventListener("error", note);
  try {
    action();
  } finally {
    window.removeEventListener("error", note);
  }
  return errors;
}

describe("what a view tells of a selection that reaches beyond it", () => {
  it("tells the passage of a selection that has both ends in it", () => {
    const { onSelection, one } = setup();

    select([one, 0], [one, 6]);
    announceSelection();

    expect(onSelection).toHaveBeenCalledTimes(1);
    expect(onSelection).toHaveBeenCalledWith({ text: "inside one", line_start: 1, line_end: 1, shown: 6 });
  });

  it("tells that nothing is selected when a selection starts in it and runs on into the page", () => {
    const { onSelection, two } = setup();

    select([two, 3], [elsewhere("below", "after"), 4]);
    announceSelection();

    expect(onSelection).toHaveBeenCalledTimes(1);
    expect(onSelection).toHaveBeenCalledWith(null);
  });

  it("tells that nothing is selected when a selection comes into it from the page", () => {
    const { onSelection, one } = setup();

    select([elsewhere("above", "before"), 1], [one, 4]);
    announceSelection();

    expect(onSelection).toHaveBeenCalledTimes(1);
    expect(onSelection).toHaveBeenCalledWith(null);
  });

  it("hears nothing of a selection that has neither end in it, even one that runs over it", () => {
    const { onSelection } = setup();
    const above = elsewhere("above", "before");
    const below = elsewhere("below", "after");

    select([below, 1], [below, 4]);
    announceSelection();
    select([above, 1], [below, 4]);
    announceSelection();

    expect(onSelection).not.toHaveBeenCalled();
  });

  it("raises nothing when a selection is made in a view that nobody listens to", () => {
    const { container } = render(<CanvasView text={SOURCE} kind="markdown" />);
    const one = find(container.querySelector(".canvas-view") as HTMLElement, "inside one").node;

    const errors = raised(() => {
      select([one, 0], [one, 6]);
      announceSelection();
    });

    expect(errors).toEqual([]);
  });

  it("raises nothing, and tells nothing more, when the selection is taken away altogether", () => {
    const { onSelection, one } = setup();
    select([one, 0], [one, 6]);
    announceSelection();

    const errors = raised(() => {
      document.getSelection()?.removeAllRanges();
      announceSelection();
    });

    expect(errors).toEqual([]);
    expect(onSelection).toHaveBeenCalledTimes(1);
  });
});
