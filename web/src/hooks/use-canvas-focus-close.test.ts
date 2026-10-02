import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { focusCalls, focusRoute, NOTE, openTab, SHOP, startDockServer } from "../test/canvas-dock-hook";
import { landed, stopServer } from "../test/canvas-hook";
import type { FakeBackend } from "../test/fake-backend";
import { useCanvasFocus } from "./use-canvas-focus";

let backend: FakeBackend;

beforeEach(() => {
  backend = startDockServer();
});

afterEach(stopServer);

const writes = (id = "c1") => focusCalls(backend, "PUT", id);
const bodies = (id = "c1") => writes(id).map((request) => request.body);

describe("closing the canvas", () => {
  it("tells the server once, from a canvas opened here, and opening it told nothing", async () => {
    const { result, rerender } = await openTab();
    act(() => result.current.open(NOTE));
    await landed();
    expect(writes()).toHaveLength(0);

    await act(() => result.current.close());
    await landed();
    rerender({ conversationId: "c1", wide: true });
    await act(() => result.current.close());
    await landed();

    expect(bodies()).toEqual([{ artifact_id: null }]);
    expect(backend.canvas.focus.of("c1")).toBeNull();
  });

  it("tells the server too when nothing was opened here, the list having been shown", async () => {
    const { result } = await openTab();

    await act(() => result.current.showList());
    await act(() => result.current.close());
    await landed();

    expect(bodies()).toEqual([{ artifact_id: null }]);
  });

  it("tells nothing when the person only goes back to the list, or on a narrow screen", async () => {
    const wide = await openTab();
    act(() => wide.result.current.open(NOTE));
    await act(() => wide.result.current.showList());
    const narrow = await openTab({ wide: false });
    act(() => narrow.result.current.open(NOTE));
    await act(() => narrow.result.current.close());
    await landed();

    expect(writes()).toHaveLength(0);
    expect(narrow.result.current).toMatchObject({ view: "closed", focusId: NOTE });
  });

  it("tells nothing when the person goes to another conversation with a canvas open", async () => {
    const { result, rerender } = await openTab();
    act(() => result.current.open(NOTE));

    rerender({ conversationId: "c2", wide: true });
    await landed();

    expect(writes("c1")).toHaveLength(0);
    expect(writes("c2")).toHaveLength(0);
  });

  it("only logs a write that failed, and the dock stays closed", async () => {
    const logged = vitest.spyOn(console, "error").mockImplementation(() => undefined);
    backend.canvas.refuseNext(`PUT ${focusRoute("c1")}`, 500);
    const { result } = await openTab();
    act(() => result.current.open(NOTE));

    await act(() => result.current.close());
    await landed();

    expect(logged).toHaveBeenCalledWith("could not tell the server the canvas was closed", expect.any(Error));
    expect(result.current).toMatchObject({ view: "closed", focusId: null });
  });
});

describe("a focus that is null without the person having closed anything", () => {
  type Dock = { conversationId: string; focusId: string | null | undefined };
  const mountWith = (start: Dock) =>
    renderHook(
      ({ conversationId, focusId }: Dock) =>
        useCanvasFocus(conversationId, false, { focusId, ticket: () => 0, restore: () => undefined }),
      { initialProps: start },
    );

  it("is not told when the hook mounts with it", async () => {
    mountWith({ conversationId: "c1", focusId: null });
    await landed();

    expect(writes()).toHaveLength(0);
  });

  it("is not told when it comes with a change of conversation, and the next close there is", async () => {
    const { rerender } = mountWith({ conversationId: "c1", focusId: NOTE });

    rerender({ conversationId: "c2", focusId: null });
    await landed();
    expect(writes("c1")).toHaveLength(0);
    expect(writes("c2")).toHaveLength(0);

    rerender({ conversationId: "c2", focusId: SHOP });
    rerender({ conversationId: "c2", focusId: null });
    await landed();
    expect(bodies("c2")).toEqual([{ artifact_id: null }]);
  });
});
