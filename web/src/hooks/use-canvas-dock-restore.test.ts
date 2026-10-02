import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { NOTE, openDock, SHOP, startDockServer } from "../test/canvas-dock-hook";
import { landed, stopServer } from "../test/canvas-hook";
import type { CanvasDock } from "./use-canvas-dock";

beforeEach(() => void startDockServer());

afterEach(stopServer);

const untouched = { view: "closed", artifactId: null, focusId: undefined } as const;

describe("opening again the canvas the server had open", () => {
  it("opens it quietly, and names it, when nothing has moved since the ticket", async () => {
    const { result } = await openDock();
    const ticket = result.current.ticket();

    act(() => result.current.restore(NOTE, ticket));

    expect(result.current).toMatchObject({
      view: "canvas",
      artifactId: NOTE,
      focusId: NOTE,
      quiet: true,
      created: false,
    });
  });

  it.each<[string, (dock: CanvasDock) => unknown, Partial<CanvasDock>]>([
    ["another canvas was opened", (dock) => dock.open(SHOP), { view: "canvas", artifactId: SHOP }],
    ["the list was opened", (dock) => dock.showList(), { view: "list", artifactId: null }],
    ["the dock was closed anyway", (dock) => dock.forceClose(), { view: "closed", artifactId: null }],
  ])("opens nothing when %s since the ticket was taken", async (_name, move, left) => {
    const { result } = await openDock();
    const ticket = result.current.ticket();
    await act(async () => void (await move(result.current)));

    act(() => result.current.restore(NOTE, ticket));

    expect(result.current).toMatchObject(left);
    expect(result.current.quiet).toBe(false);
  });

  it("opens nothing once the person went to another conversation and came back", async () => {
    const { result, rerender } = await openDock();
    const ticket = result.current.ticket();
    rerender({ conversationId: "c2", wide: true });
    rerender({ conversationId: "c1", wide: true });
    await landed();

    act(() => result.current.restore(NOTE, ticket));

    expect(result.current).toMatchObject(untouched);
  });

  it("opens nothing, here or on the way back, through a reference taken in the conversation left", async () => {
    const { result, rerender } = await openDock();
    const { restore } = result.current;
    rerender({ conversationId: "c2", wide: true });
    await landed();
    const ticket = result.current.ticket();

    act(() => restore(NOTE, ticket));
    expect(result.current).toMatchObject(untouched);

    // A reference of the old conversation that got through would wait here, hidden, until now.
    rerender({ conversationId: "c1", wide: true });
    await landed();
    expect(result.current).toMatchObject(untouched);
  });

  it.each(["a1", "../x", "0123456789AB", "0123456789a", "0123456789abc", "0123456789ab\n", ""])(
    "opens nothing for %j, which the server never made as an id",
    async (id) => {
      const { result } = await openDock();

      act(() => result.current.restore(id, result.current.ticket()));

      expect(result.current).toMatchObject(untouched);
    },
  );
});
