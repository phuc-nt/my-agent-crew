import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import type { ThreadItem, ToolStatus } from "../state/thread-reducer";
import { useCanvasAutoOpen } from "./use-canvas-auto-open";

const NOTE = "0123456789ab";
const SHOP = "ba9876543210";

type Props = { items: ThreadItem[]; shown: string | null };

const made = (id: string, canvas: string, status: ToolStatus = "done"): ThreadItem => ({
  kind: "tool",
  id,
  name: "artifact_create",
  arguments: {},
  output: status === "done" ? `[artifact ${canvas} v1]\nCanvas was created.` : null,
  status,
});

/** The hook beside a dock that is showing the canvas call `shown` is writing, if any. */
function mount(shown: string | null) {
  const dock = { open: vitest.fn(), typing: () => false };
  let props: Props = { items: [], shown };
  const view = renderHook(
    (now: Props) => useCanvasAutoOpen({ state: { items: now.items }, detail: null }, dock, true, now.shown),
    { initialProps: props },
  );
  const update = (next: Partial<Props>) => {
    props = { ...props, ...next };
    view.rerender(props);
  };
  return { dock, update };
}

describe("a canvas the dock showed while it was written", () => {
  it("is left to the view that showed it, and is not opened here once that view is gone", () => {
    const { dock, update } = mount("w1");
    update({ items: [made("w1", NOTE, "running")] });

    update({ items: [made("w1", NOTE)] });
    expect(dock.open).not.toHaveBeenCalled();

    update({ shown: null });
    update({ items: [made("w1", NOTE), { kind: "assistant", id: "a1", text: "Xong.", model: null }] });
    expect(dock.open).not.toHaveBeenCalled();
  });

  it("does not keep the other canvases of the turn from opening", () => {
    const { dock, update } = mount("w1");

    update({ items: [made("w0", SHOP), made("w1", NOTE)] });

    expect(dock.open.mock.calls).toEqual([[SHOP, { quiet: true }]]);
  });

  it("opens as ever when nothing is shown", () => {
    const { dock, update } = mount(null);

    update({ items: [made("w1", NOTE)] });

    expect(dock.open.mock.calls).toEqual([[NOTE, { quiet: true }]]);
  });
});
