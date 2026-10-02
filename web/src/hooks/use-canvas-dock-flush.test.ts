import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { handoffsSettled, saveInBackground } from "../lib/canvas-handoff";
import { openState } from "../lib/canvas-machine";
import { NOTE, openDock, opened, panel, SHOP, startDockServer } from "../test/canvas-dock-hook";
import { landed, stopServer, wait, watch } from "../test/canvas-hook";
import { DOCK_FLUSH_MS } from "./use-canvas-dock";

const held: Array<() => void> = [];

beforeEach(() => void startDockServer());

// The saves left out are module state: one still out would hold up the next test's flush.
afterEach(async () => {
  for (const release of held.splice(0)) release();
  await handoffsSettled();
  stopServer();
});

/** A save left in the background that stays out until the test lets it go. */
function leaveSaveOut(id = SHOP) {
  let release!: (version: number | null) => void;
  const flush = () => new Promise<number | null>((resolve) => (release = resolve));
  saveInBackground({ id, state: openState(id, null), flush });
  held.push(() => release(1));
  return (version: number | null = 1) => release(version);
}

describe("flush", () => {
  it("answers the version the open panel's last save landed", async () => {
    const { result } = await openDock();
    opened(result, NOTE, panel(Promise.resolve(4)));

    await expect(result.current.flush()).resolves.toBe(4);
  });

  it("answers null when no version holds the text within the cap", async () => {
    const { result } = await openDock();
    opened(result, NOTE, panel());
    const answer = watch(result.current.flush());

    wait(DOCK_FLUSH_MS - 1);
    await landed();
    expect(answer.settled).toBe(false);
    wait(1);
    await landed();

    expect(answer).toEqual({ settled: true, value: null });
  });

  it("waits for the save of a canvas left earlier, and keeps the panel's version when that save is late", async () => {
    const { result } = await openDock();
    opened(result, NOTE, panel(Promise.resolve(4)));
    leaveSaveOut();
    const answer = watch(result.current.flush());

    await landed();
    expect(answer.settled).toBe(false);
    wait(DOCK_FLUSH_MS);
    await landed();

    expect(answer).toEqual({ settled: true, value: 4 });
  });

  it("waits for the saves of canvases left earlier when no panel is open, and answers null", async () => {
    const { result } = await openDock();
    const release = leaveSaveOut();
    const answer = watch(result.current.flush());

    wait(1000);
    await landed();
    expect(answer.settled).toBe(false);
    release(1);
    await landed();

    expect(answer).toEqual({ settled: true, value: null });
  });

  it("is one function for as long as the dock is mounted", async () => {
    const { result, rerender } = await openDock();
    const { flush } = result.current;

    opened(result);
    rerender({ conversationId: "c2", wide: false });

    expect(result.current.flush).toBe(flush);
  });

  it("is not waited on by leaving the canvas by hand, which asks the open panel alone", async () => {
    const { result } = await openDock();
    opened(result, NOTE, panel(Promise.resolve(3)));
    leaveSaveOut();
    let closing = { settled: false };

    act(() => {
      closing = watch(result.current.close());
    });
    await landed();

    expect(closing.settled).toBe(true);
    expect(result.current).toMatchObject({ view: "closed", stuck: false });
  });
});
