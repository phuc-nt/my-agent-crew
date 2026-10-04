import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, type Mock, vi as vitest } from "vitest";
import type { ArtifactEvent } from "../api/artifact-types";
import { onArtifactEvent } from "../lib/artifact-events";
import { landed, startServer, stopServer, wait } from "../test/canvas-hook";
import type { FakeBackend } from "../test/fake-backend";
import { useCanvasLibrary } from "./use-canvas-library";
import { LIST_RELOAD_MS } from "./use-canvas-list";

const ONE = "0123456789ab";

let backend: FakeBackend;
let heard: Mock<(event: ArtifactEvent) => void>;
let unsubscribe: () => void;

beforeEach(() => {
  backend = startServer();
  backend.canvas.add({ id: ONE, title: "Một", content: "abc" });
  backend.canvas.add({ title: "Hai", content: "de" });
  heard = vitest.fn();
});

afterEach(() => {
  unsubscribe();
  stopServer();
});

/** The library with both canvases in, on a stream that says nothing: every announcement a test
 *  hears from here on is the library's own. */
async function openLibrary() {
  const view = renderHook(() => useCanvasLibrary(true));
  await landed();
  backend.canvas.onEvent = null;
  unsubscribe = onArtifactEvent(heard);
  return view;
}

const deletes = () => backend.requests.filter((r) => r.method === "DELETE").map((r) => r.path);
const titles = (items: { title: string }[] | null) => items?.map((item) => item.title) ?? null;
const DELETED = { type: "artifact", artifact: { id: ONE, deleted: true }, conversation_ids: [] };

describe("deleting a canvas from the library", () => {
  it("drops the canvas and what it held as the server answers, and tells whatever else shows it", async () => {
    const { result } = await openLibrary();

    await act(() => result.current.remove(ONE));

    expect(deletes()).toEqual([`/artifacts/${ONE}`]);
    expect(titles(result.current.items)).toEqual(["Hai"]);
    expect(result.current.usage).toEqual({ count: 1, bytes: 2, cap: backend.canvas.storageCap, by_artifact: { a2: 2 } });
    expect(heard.mock.calls).toEqual([[DELETED]]);
    expect(result.current.refused.size).toBe(0);
  });

  it("keeps the canvas until the server has answered", async () => {
    const { result } = await openLibrary();
    const answer = backend.canvas.holdNext("DELETE", "reply");

    let done = false;
    act(() => void result.current.remove(ONE).then(() => (done = true)));
    await landed();
    expect(titles(result.current.items)).toEqual(["Hai", "Một"]);
    expect(heard).not.toHaveBeenCalled();

    await act(() => answer());
    await landed();
    expect(done).toBe(true);
    expect(titles(result.current.items)).toEqual(["Hai"]);
  });

  // Deleted in another tab, on a stream that was down: the server's 404 says what the person asked for.
  it("counts a canvas the server no longer has as deleted", async () => {
    const { result } = await openLibrary();
    backend.canvas.remove(ONE);

    await act(() => result.current.remove(ONE));

    expect(titles(result.current.items)).toEqual(["Hai"]);
    expect(result.current.usage).toMatchObject({ count: 1, bytes: 2 });
    expect(heard.mock.calls).toEqual([[DELETED]]);
    expect(result.current.refused.size).toBe(0);
  });

  it("keeps a canvas the server would not delete, and says which, until it is tried again", async () => {
    const { result } = await openLibrary();
    backend.canvas.refuseNext("DELETE", 503);

    await act(() => result.current.remove(ONE));

    expect(titles(result.current.items)).toEqual(["Hai", "Một"]);
    expect(result.current.usage).toMatchObject({ count: 2, bytes: 5 });
    expect([...result.current.refused]).toEqual([ONE]);
    expect(heard).not.toHaveBeenCalled();

    const again = backend.canvas.holdNext("DELETE", "request");
    act(() => void result.current.remove(ONE));
    await landed();
    expect(result.current.refused.size).toBe(0);
    await act(() => again());
    await landed();
    expect(titles(result.current.items)).toEqual(["Hai"]);
  });

  it("keeps a canvas when the request never reached the server", async () => {
    const { result } = await openLibrary();
    vitest.stubGlobal("fetch", () => Promise.reject(new TypeError("Failed to fetch")));

    await act(() => result.current.remove(ONE));

    expect(titles(result.current.items)).toEqual(["Hai", "Một"]);
    expect([...result.current.refused]).toEqual([ONE]);
    expect(heard).not.toHaveBeenCalled();
  });

  // A canvas made after the sizes were read has none to take off the total.
  it("leaves the total alone for a canvas whose size it never read", async () => {
    const { result } = await openLibrary();
    const late = backend.canvas.add({ title: "Ba", content: "xyz" });

    await act(() => result.current.remove(late.id));

    expect(result.current.usage).toMatchObject({ count: 2, bytes: 5 });
  });

  it("reads the library again after its own announcement, as after any other", async () => {
    const { result } = await openLibrary();
    const reads = () => backend.requests.filter((r) => r.path.startsWith("/artifacts?")).length;
    const before = reads();

    await act(() => result.current.remove(ONE));
    wait(LIST_RELOAD_MS);
    await landed();

    expect(reads()).toBe(before + 1);
    expect(titles(result.current.items)).toEqual(["Hai"]);
  });
});
