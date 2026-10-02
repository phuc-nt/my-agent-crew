import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { NOTE, openDock, opened, panel, SHOP, startDockServer } from "../test/canvas-dock-hook";
import { landed, stopServer } from "../test/canvas-hook";
import type { CanvasDock } from "./use-canvas-dock";

beforeEach(() => void startDockServer());

afterEach(stopServer);

const closers: [string, (dock: CanvasDock) => unknown][] = [
  ["close", (dock) => dock.close()],
  ["forceClose", (dock) => dock.forceClose()],
  ["toggle", (dock) => dock.toggle()],
];

describe("the canvas a message names", () => {
  it("is nothing until a canvas is opened here, then that canvas with nothing selected", async () => {
    const { result } = await openDock();
    expect(result.current.focusId).toBeUndefined();
    expect(result.current.messageCanvas()).toBeUndefined();

    opened(result);

    expect(result.current.focusId).toBe(NOTE);
    expect(result.current.messageCanvas()).toEqual({ artifact_id: NOTE, selection: null });
  });

  it("is the newest canvas opened, and a canvas made here from the moment it opens", async () => {
    const { result } = await openDock();
    opened(result, NOTE);
    opened(result, SHOP);
    expect(result.current.focusId).toBe(SHOP);

    await act(() => result.current.create());

    expect(result.current).toMatchObject({ view: "canvas", created: true });
    expect(result.current.artifactId).not.toBe(SHOP);
    expect(result.current.focusId).toBe(result.current.artifactId);
  });

  it.each(closers)("is 'none' once the person closed the canvas on a wide screen, by %s", async (_name, close) => {
    const { result } = await openDock(true);
    opened(result);

    await act(async () => void (await close(result.current)));

    expect(result.current).toMatchObject({ view: "closed", focusId: null });
    expect(result.current.messageCanvas()).toEqual({ artifact_id: null });
  });

  it.each(closers)("is still the canvas after %s puts the overlay of a narrow screen away", async (_name, close) => {
    const { result } = await openDock(false);
    opened(result);

    await act(async () => void (await close(result.current)));

    expect(result.current).toMatchObject({ view: "closed", focusId: NOTE });
    expect(result.current.messageCanvas()).toEqual({ artifact_id: NOTE, selection: null });
  });

  it("follows the width the screen has when the canvas is closed, not when it was opened", async () => {
    const { result, rerender } = await openDock(true);
    opened(result);
    rerender({ conversationId: "c1", wide: false });
    await act(() => result.current.close());
    expect(result.current.focusId).toBe(NOTE);

    opened(result);
    rerender({ conversationId: "c1", wide: true });
    await act(() => result.current.close());
    expect(result.current.focusId).toBeNull();
  });

  it.each([true, false])("is still the canvas when the person goes back to the list (wide: %s)", async (wide) => {
    const { result } = await openDock(wide);
    opened(result);

    await act(() => result.current.showList());

    expect(result.current).toMatchObject({ view: "list", focusId: NOTE });
  });

  it("is still the canvas while a close waits on a save that did not land", async () => {
    const { result } = await openDock();
    opened(result, NOTE, panel(Promise.resolve(null)));

    await act(() => result.current.close());

    expect(result.current).toMatchObject({ view: "canvas", stuck: true, focusId: NOTE });
    expect(result.current.messageCanvas()).toEqual({ artifact_id: NOTE, selection: null });
  });

  it("starts empty in another conversation, and does not come back with the person", async () => {
    const { result, rerender } = await openDock();
    opened(result);

    rerender({ conversationId: "c2", wide: true });
    expect(result.current.focusId).toBeUndefined();
    expect(result.current.messageCanvas()).toBeUndefined();

    await landed();
    rerender({ conversationId: "c1", wide: true });
    await landed();
    expect(result.current.focusId).toBeUndefined();
  });

  it("is read as it stands when asked, through a reference taken before", async () => {
    const { result } = await openDock();
    const { messageCanvas } = result.current;
    expect(messageCanvas()).toBeUndefined();

    opened(result);

    expect(messageCanvas()).toEqual({ artifact_id: NOTE, selection: null });
    expect(result.current.messageCanvas).toBe(messageCanvas);
  });
});

describe("a canvas opened quietly", () => {
  it("is marked until the next move, and an ordinary opening is not marked", async () => {
    const { result } = await openDock();
    act(() => result.current.open(NOTE));
    expect(result.current.quiet).toBe(false);

    act(() => result.current.open(SHOP, { quiet: true }));
    expect(result.current).toMatchObject({ artifactId: SHOP, focusId: SHOP, quiet: true });

    act(() => result.current.open(NOTE));
    expect(result.current.quiet).toBe(false);
  });

  it.each<[string, (dock: CanvasDock) => unknown]>([
    ["another canvas opens", (dock) => dock.open(NOTE)],
    ["the list opens", (dock) => dock.showList()],
    ["the dock closes", (dock) => dock.close()],
    ["the dock is closed anyway", (dock) => dock.forceClose()],
  ])("is no longer marked once %s", async (_name, move) => {
    const { result } = await openDock();
    act(() => result.current.open(SHOP, { quiet: true }));

    await act(async () => void (await move(result.current)));

    expect(result.current.quiet).toBe(false);
  });
});
