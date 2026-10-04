import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi as vitest } from "vitest";
import type { ThreadItem, ToolStatus } from "../state/thread-reducer";
import { useCanvasAutoOpen } from "./use-canvas-auto-open";

const NOTE = "0123456789ab";
const SHOP = "ba9876543210";

type Tool = Extract<ThreadItem, { kind: "tool" }>;

/** A file read into canvas `canvas`: the tag opens a finished call's result, as the server writes it. */
function imported(id: string, args: Record<string, unknown>, options: { status?: ToolStatus; unchanged?: boolean; canvas?: string } = {}): Tool {
  const { status = "done", unchanged = false, canvas = NOTE } = options;
  const output = status === "done" ? `[artifact ${canvas} v1${unchanged ? " unchanged" : ""}]\nImported.` : null;
  return { kind: "tool", id, name: "artifact_import", arguments: { path: "notes/thuc-don.md", ...args }, output, status };
}

/** The conversation as the server gave it, holding the calls `ids` name. */
const history = (...ids: string[]) => ({ messages: [{ tool_calls: ids.map((id) => ({ id })) }] });

/**
 * The hook as the chat screen runs it on a wide screen, with nobody typing; `open` is recorded.
 * `detail` is the conversation read from the server, null for one just made.
 */
function mount(detail: ReturnType<typeof history> | null = null) {
  const dock = { open: vitest.fn(), typing: vitest.fn(() => false) };
  const view = renderHook((items: ThreadItem[]) => useCanvasAutoOpen({ state: { items }, detail }, dock, true), {
    initialProps: [] as ThreadItem[],
  });
  return { dock, draw: (items: ThreadItem[]) => view.rerender(items) };
}

describe("opening the canvas a file was just read into", () => {
  it("opens it quietly when the call named no canvas, for it made one", () => {
    const { dock, draw } = mount();

    draw([imported("c1", {})]);

    expect(dock.open.mock.calls).toEqual([[NOTE, { quiet: true }]]);
  });

  it("takes an id sent blank, or as anything but text, as none", () => {
    const { dock, draw } = mount();

    draw([imported("c1", { id: "" }), imported("c2", { id: "  " }, { canvas: SHOP }), imported("c3", { id: null })]);

    expect(dock.open.mock.calls.map(([id]) => id)).toEqual([NOTE, SHOP, NOTE]);
  });

  it("takes for blank an id the server strips to nothing, though trim would leave it", () => {
    const { dock, draw } = mount();

    draw([imported("c1", { id: "\u{1F}" }), imported("c2", { id: "\u{85}\u{1C}" }, { canvas: SHOP })]);

    expect(dock.open.mock.calls.map(([id]) => id)).toEqual([NOTE, SHOP]);
  });

  it("does not open a canvas the call named, which a file was read into again", () => {
    const { dock, draw } = mount();

    draw([imported("c1", { id: NOTE, replace: true })]);

    expect(dock.open).not.toHaveBeenCalled();
  });

  it("does not open a canvas the file left as it was", () => {
    const { dock, draw } = mount();

    draw([imported("c1", {}, { unchanged: true })]);

    expect(dock.open).not.toHaveBeenCalled();
  });

  it("waits for the call to end, and does not open for one that failed or was refused", () => {
    const { dock, draw } = mount();

    draw([imported("c1", {}, { status: "running" }), imported("c2", {}, { status: "failed" }), imported("c3", {}, { status: "denied" })]);
    expect(dock.open).not.toHaveBeenCalled();

    draw([imported("c1", {}), imported("c2", {}, { status: "failed" }), imported("c3", {}, { status: "denied" })]);
    expect(dock.open.mock.calls).toEqual([[NOTE, { quiet: true }]]);
  });

  it("does not open for an import the conversation's saved history holds, only for one of this turn", () => {
    const { dock, draw } = mount(history("c1"));

    // Both arrive after the screen was drawn; the server's copy of the conversation names the first.
    draw([imported("c1", {}), imported("c2", {}, { canvas: SHOP })]);

    expect(dock.open.mock.calls).toEqual([[SHOP, { quiet: true }]]);
  });

  it("does not open for a canvas written out to a file, whatever its result says", () => {
    const { dock, draw } = mount();

    draw([{ ...imported("c1", { id: NOTE }), name: "artifact_export" }, { ...imported("c2", {}), name: "artifact_export" }]);

    expect(dock.open).not.toHaveBeenCalled();
  });
});
