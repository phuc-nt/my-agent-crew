import { act } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { focusCalls, focusRoute, NOTE, openTab, SHOP, startDockServer } from "../test/canvas-dock-hook";
import { landed, stopServer } from "../test/canvas-hook";
import type { FakeBackend } from "../test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = startDockServer();
});

afterEach(stopServer);

const reads = (id = "c1") => focusCalls(backend, "GET", id);
const writes = (id = "c1") => focusCalls(backend, "PUT", id);
const serverHas = (conversation: string, id: string) => backend.canvas.focus.open(conversation, id);
const untouched = { view: "closed", artifactId: null, focusId: undefined } as const;

describe("coming into a conversation", () => {
  it("opens, quietly, the canvas the server has open there, on a wide screen, and writes nothing", async () => {
    serverHas("c1", NOTE);

    const { result } = await openTab();

    expect(reads()).toHaveLength(1);
    expect(result.current).toMatchObject({ view: "canvas", artifactId: NOTE, focusId: NOTE, quiet: true });
    expect(writes()).toHaveLength(0);
  });

  it("opens nothing when the server has no canvas open there, and leaves a message free of one", async () => {
    const { result } = await openTab();

    expect(reads()).toHaveLength(1);
    expect(result.current).toMatchObject(untouched);
    expect(result.current.messageCanvas()).toBeUndefined();
  });

  it("asks again in each conversation it changes to, and opens the canvas of that one", async () => {
    serverHas("c1", NOTE);
    serverHas("c2", SHOP);
    const { result, rerender } = await openTab();

    rerender({ conversationId: "c2", wide: true });
    await landed();

    expect(reads("c2")).toHaveLength(1);
    expect(result.current).toMatchObject({ view: "canvas", artifactId: SHOP, focusId: SHOP });
    expect(writes("c1")).toHaveLength(0);
    expect(writes("c2")).toHaveLength(0);
  });

  it("asks nothing on a narrow screen, and nothing again when the screen turns wide or the dock moves", async () => {
    serverHas("c1", NOTE);
    const { result, rerender } = await openTab({ wide: false });
    expect(reads()).toHaveLength(0);
    expect(result.current.view).toBe("closed");

    rerender({ conversationId: "c1", wide: true });
    act(() => result.current.open(SHOP));
    await act(() => result.current.close());
    await landed();

    expect(reads()).toHaveLength(0);
  });

  it("opens nothing for an id the server never makes", async () => {
    backend.canvas.add({ id: "a1", title: "Lạ" });
    serverHas("c1", "a1");

    const { result } = await openTab();

    expect(reads()).toHaveLength(1);
    expect(result.current).toMatchObject(untouched);
  });

  it("opens the canvas once, and writes nothing, under StrictMode's second run of the effect", async () => {
    serverHas("c1", NOTE);

    const { result } = await openTab({}, StrictMode);

    expect(reads()).toHaveLength(2);
    expect(result.current).toMatchObject({ view: "canvas", artifactId: NOTE, quiet: true });
    expect(writes()).toHaveLength(0);
  });

  it("opens nothing when the answer comes after the person went to another conversation", async () => {
    serverHas("c1", NOTE);
    const release = backend.canvas.holdNext(`GET ${focusRoute("c1")}`, "reply");
    const { result, rerender } = await openTab();

    rerender({ conversationId: "c2", wide: true });
    await landed();
    await act(() => release());
    await landed();

    expect(result.current).toMatchObject(untouched);
  });

  it("opens nothing when the answer comes after the person opened a canvas and closed it again", async () => {
    serverHas("c1", NOTE);
    const release = backend.canvas.holdNext(`GET ${focusRoute("c1")}`, "reply");
    const { result } = await openTab();

    act(() => result.current.open(SHOP));
    await act(() => result.current.close());
    await act(() => release());
    await landed();

    expect(result.current).toMatchObject({ view: "closed", artifactId: null, focusId: null });
  });

  it("only logs a read that failed, and the dock stays usable", async () => {
    const logged = vitest.spyOn(console, "error").mockImplementation(() => undefined);
    backend.canvas.refuseNext(`GET ${focusRoute("c1")}`, 500);

    const { result } = await openTab();
    act(() => result.current.open(NOTE));

    expect(logged).toHaveBeenCalledWith("could not read the canvas open in this conversation", expect.any(Error));
    expect(result.current).toMatchObject({ view: "canvas", artifactId: NOTE });
  });
});
