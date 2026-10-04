import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { handoffsSettled, saveInBackground } from "../lib/canvas-handoff";
import { NOTE, openDock, opened, panel, SHOP, startDockServer } from "../test/canvas-dock-hook";
import { landed, stopServer, wait, watch } from "../test/canvas-hook";
import { type LeftCanvas, leftCanvas } from "../test/canvas-left";
import { DOCK_FLUSH_MS } from "./use-canvas-dock";

const held: Array<() => void> = [];

beforeEach(() => void startDockServer());

// The saves left out are module state: one still out would hold up the next test's wait.
afterEach(async () => {
  for (const release of held.splice(0)) release();
  await handoffsSettled();
  stopServer();
});

/** A save left in the background that stays out until the test ends. */
function leaveSaveOut(id: string, over: Partial<LeftCanvas> = {}) {
  let release!: (version: number | null) => void;
  const flush = () => new Promise<number | null>((resolve) => (release = resolve));
  saveInBackground(leftCanvas(id, flush, over));
  held.push(() => release(1));
}

/** A save in flight that was first given a minute, and ten after the saves before it had no reply in time. */
const stretched = (first?: boolean) => (first ? 60_000 : 600_000);

describe("the wait of a message on a save given longer after saves that had no reply in time", () => {
  it("is the deadline the open panel's save was first given, and the cap after it", async () => {
    const { result } = await openDock();
    opened(result, NOTE, { ...panel(), waitMs: stretched });
    const answer = watch(result.current.flush());

    wait(DOCK_FLUSH_MS + 60_000 - 1);
    await landed();
    expect(answer.settled).toBe(false);
    wait(1);
    await landed();

    expect(answer).toEqual({ settled: true, value: null });
  });

  it("is the deadline the save of a canvas left behind was first given, too", async () => {
    const { result } = await openDock();
    leaveSaveOut(SHOP, { waitMs: stretched });
    const answer = watch(result.current.flush());

    wait(DOCK_FLUSH_MS + 60_000 - 1);
    await landed();
    expect(answer.settled).toBe(false);
    wait(1);
    await landed();

    expect(answer).toEqual({ settled: true, value: null });
  });
});

describe("whether a message about to go names a canvas with text no version holds", () => {
  it("is not so where no canvas was opened", async () => {
    const { result } = await openDock();

    await expect(result.current.flushForMessage()).resolves.toBe(false);
  });

  it("is not so once the open canvas's last save has landed", async () => {
    const { result } = await openDock();
    opened(result, NOTE, panel(Promise.resolve(4)));

    await expect(result.current.flushForMessage()).resolves.toBe(false);
  });

  it("is so when the open canvas's last save failed", async () => {
    const { result } = await openDock();
    opened(result, NOTE, panel(Promise.resolve(null)));

    await expect(result.current.flushForMessage()).resolves.toBe(true);
  });

  it("is so when that save has not landed by the end of the wait, and is not said before", async () => {
    const { result } = await openDock();
    opened(result, NOTE, { ...panel(), waitMs: stretched });
    const answer = watch(result.current.flushForMessage());

    wait(DOCK_FLUSH_MS + 60_000 - 1);
    await landed();
    expect(answer.settled).toBe(false);
    wait(1);
    await landed();

    expect(answer).toEqual({ settled: true, value: true });
  });

  it("is not so of a canvas that is gone: there is no version for the message to go with", async () => {
    const { result } = await openDock();
    opened(result, NOTE, { ...panel(Promise.resolve(null)), gone: () => true });

    await expect(result.current.flushForMessage()).resolves.toBe(false);
  });

  it("is so when the canvas it names was put away with its last save still out", async () => {
    const { result } = await openDock(false);
    opened(result);
    await act(() => result.current.close());
    expect(result.current).toMatchObject({ view: "closed", focusId: NOTE });
    leaveSaveOut(NOTE);
    const answer = watch(result.current.flushForMessage());

    wait(DOCK_FLUSH_MS);
    await landed();

    expect(answer).toEqual({ settled: true, value: true });
  });

  it("is not so when the save still out is of another canvas than the one it names", async () => {
    const { result } = await openDock(false);
    opened(result);
    await act(() => result.current.close());
    leaveSaveOut(SHOP);
    const answer = watch(result.current.flushForMessage());

    wait(DOCK_FLUSH_MS);
    await landed();

    expect(answer).toEqual({ settled: true, value: false });
  });

  it("is not so where a save is still out and the message names no canvas", async () => {
    const { result } = await openDock();
    leaveSaveOut(NOTE);
    const answer = watch(result.current.flushForMessage());

    wait(DOCK_FLUSH_MS);
    await landed();

    expect(answer).toEqual({ settled: true, value: false });
  });

  it("is not said of a canvas opened while the message waited on another one's save", async () => {
    const { result } = await openDock();
    act(() => result.current.open(NOTE));
    let unbind = () => {};
    act(() => {
      unbind = result.current.bind(panel());
    });
    const answer = watch(result.current.flushForMessage());

    // The person opens another canvas: the first panel goes, and the next lends its own handle.
    act(() => unbind());
    opened(result, SHOP, panel(Promise.resolve(2)));
    wait(DOCK_FLUSH_MS);
    await landed();

    expect(answer).toEqual({ settled: true, value: false });
  });
});

describe("the note that a message went before the canvas it names was saved", () => {
  it("is not there until such a message has gone, and goes with the next one whose canvas was saved", async () => {
    const { result } = await openDock();
    expect(result.current.sentUnsaved).toBe(false);

    act(() => result.current.noteSentUnsaved(true));
    expect(result.current.sentUnsaved).toBe(true);

    act(() => result.current.noteSentUnsaved(false));
    expect(result.current.sentUnsaved).toBe(false);
  });

  it("stays with the conversation the message went in: another one does not show it, and coming back does", async () => {
    const { result, rerender } = await openDock();
    act(() => result.current.noteSentUnsaved(true));

    rerender({ conversationId: "c2", wide: true });
    expect(result.current.sentUnsaved).toBe(false);

    rerender({ conversationId: "c1", wide: true });
    expect(result.current.sentUnsaved).toBe(true);
  });

  it("is about the conversation the message was sent in, though the person has since opened another", async () => {
    const { result, rerender } = await openDock();
    const said = result.current.noteSentUnsaved;

    rerender({ conversationId: "c2", wide: true });
    act(() => said(true));
    expect(result.current.sentUnsaved).toBe(false);

    rerender({ conversationId: "c1", wide: true });
    expect(result.current.sentUnsaved).toBe(true);
  });

  it("is each conversation's own: a message that went with its canvas saved in one leaves the other's", async () => {
    const { result, rerender } = await openDock();
    act(() => result.current.noteSentUnsaved(true));
    rerender({ conversationId: "c2", wide: true });

    act(() => result.current.noteSentUnsaved(false));
    rerender({ conversationId: "c1", wide: true });
    expect(result.current.sentUnsaved).toBe(true);

    rerender({ conversationId: "c2", wide: true });
    act(() => result.current.noteSentUnsaved(true));
    expect(result.current.sentUnsaved).toBe(true);
    rerender({ conversationId: "c1", wide: true });
    expect(result.current.sentUnsaved).toBe(true);

    act(() => result.current.noteSentUnsaved(false));
    expect(result.current.sentUnsaved).toBe(false);
    rerender({ conversationId: "c2", wide: true });
    expect(result.current.sentUnsaved).toBe(true);
  });

  it("is never there where no conversation is open", async () => {
    const { result, rerender } = await openDock();
    rerender({ conversationId: null, wide: true });

    act(() => result.current.noteSentUnsaved(true));

    expect(result.current.sentUnsaved).toBe(false);
  });
});
