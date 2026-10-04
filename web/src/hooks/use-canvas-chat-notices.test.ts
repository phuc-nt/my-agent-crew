import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { canvasSaved, saveInBackground } from "../lib/canvas-handoff";
import { leftCanvas } from "../test/canvas-left";
import { useCanvasChatNotices } from "./use-canvas-chat-notices";

/** The last save of canvas `id` fails after its panel went; `tabOnly` when this device kept no draft of it. */
const failedSave = (id: string, tabOnly = false) =>
  saveInBackground(leftCanvas(id, async () => null, { draftFailed: tabOnly }));

async function told(...ids: string[]) {
  const view = renderHook(() => useCanvasChatNotices("c1"));
  for (const id of ids) await act(() => failedSave(id));
  return view;
}

describe("what the chat says of a save that failed after its panel went", () => {
  it("is said no more once that canvas is saved, and still said of the others", async () => {
    const { result } = await told("a1", "a2");
    expect(result.current.handoffs.map((failure) => failure.id)).toEqual(["a1", "a2"]);

    act(() => canvasSaved("a1"));

    expect(result.current.handoffs).toEqual([{ id: "a2", title: null, draft: true }]);
  });

  it("goes the same when only this tab held the draft", async () => {
    const { result } = renderHook(() => useCanvasChatNotices("c1"));
    await act(() => failedSave("a1", true));
    expect(result.current.handoffs).toEqual([{ id: "a1", title: null, draft: false }]);

    act(() => canvasSaved("a1"));

    expect(result.current.handoffs).toEqual([]);
  });

  it("goes when a later save of that canvas, left behind again, lands", async () => {
    const { result } = await told("a1");

    await act(() => saveInBackground(leftCanvas("a1", async () => 4)));

    expect(result.current.handoffs).toEqual([]);
  });

  it("is the same list, untouched, when a canvas nobody spoke of is saved", async () => {
    const { result } = await told("a1");
    const before = result.current.handoffs;

    act(() => canvasSaved("a2"));

    expect(result.current.handoffs).toBe(before);
  });

  it("is said again when that canvas's save fails after it was saved", async () => {
    const { result } = await told("a1");
    act(() => canvasSaved("a1"));

    await act(() => failedSave("a1"));

    expect(result.current.handoffs).toEqual([{ id: "a1", title: null, draft: true }]);
  });

  it("is put away by the person as before", async () => {
    const { result } = await told("a1", "a2");

    act(() => result.current.dismissHandoff("a2"));

    expect(result.current.handoffs.map((failure) => failure.id)).toEqual(["a1"]);
  });
});
