import { render } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import { CanvasView } from "./canvas-view";

const drawn = vitest.hoisted(() => ({ times: 0 }));

// The real body, counted each time it is drawn.
vitest.mock("../markdown-body", async (importOriginal) => {
  const real = await importOriginal<typeof import("../markdown-body")>();
  const { createElement } = await import("react");
  return {
    ...real,
    MarkdownBody: (props: Parameters<typeof real.MarkdownBody>[0]) => {
      drawn.times += 1;
      return createElement(real.MarkdownBody, props);
    },
  };
});

describe("the text of a view drawn again", () => {
  const onSelection = () => {};

  it("is left alone when what the view is given is the same as before", () => {
    const { rerender } = render(<CanvasView text="# Title" kind="markdown" onSelection={onSelection} />);
    const first = drawn.times;
    expect(first).toBeGreaterThan(0);

    rerender(<CanvasView text="# Title" kind="markdown" onSelection={onSelection} />);

    expect(drawn.times).toBe(first);
  });

  it("is drawn again when the text it is given changes", () => {
    const { rerender } = render(<CanvasView text="# Title" kind="markdown" onSelection={onSelection} />);
    const first = drawn.times;

    rerender(<CanvasView text="# Another" kind="markdown" onSelection={onSelection} />);

    expect(drawn.times).toBeGreaterThan(first);
  });
});
