import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { artifactApi } from "../api/artifact-client";
import { emitArtifactEvent } from "../lib/artifact-events";
import { landed, setVisibility, startServer, stopServer, wait } from "../test/canvas-hook";
import type { FakeBackend } from "../test/fake-backend";
import { LIBRARY_LIMIT, SEARCH_WAIT_MS, useCanvasLibrary } from "./use-canvas-library";
import { LIST_RELOAD_MS } from "./use-canvas-list";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
});

afterEach(stopServer);

async function openLibrary(connected = true) {
  const view = renderHook((p: { connected: boolean }) => useCanvasLibrary(p.connected), { initialProps: { connected } });
  await landed();
  return view;
}

const lists = () => backend.requests.filter((r) => r.method === "GET" && r.path.startsWith("/artifacts?")).map((r) => r.path);
const counts = () => backend.requests.filter((r) => r.path === "/artifacts/usage");
const asked = (path: string) => Object.fromEntries(new URLSearchParams(path.split("?")[1]));
const titles = (items: { title: string }[] | null) => items?.map((item) => item.title) ?? null;

/** Types `words` and lets the wait after the last key run out. */
async function search(view: Awaited<ReturnType<typeof openLibrary>>, words: string) {
  act(() => view.result.current.setQuery(words));
  wait(SEARCH_WAIT_MS);
  await landed();
}

/** Lets each held reply through, in the order given. */
async function release(...gates: (() => Promise<void>)[]) {
  for (const open of gates) await act(() => open());
  await landed();
}

describe("reading the library", () => {
  it("reads every canvas, whatever conversation it is linked to, and what each one holds", async () => {
    backend.canvas.add({ title: "Cũ", conversationIds: ["c1"] });
    backend.canvas.add({ title: "Mới", content: "ab" });

    const { result } = await openLibrary();

    expect(lists()).toEqual([`/artifacts?limit=${LIBRARY_LIMIT}`]);
    expect(counts()).toHaveLength(1);
    expect(titles(result.current.items)).toEqual(["Mới", "Cũ"]);
    expect(result.current.usage).toEqual({ count: 2, bytes: 2, cap: backend.canvas.storageCap, by_artifact: { a1: 0, a2: 2 } });
    expect(result.current).toMatchObject({ query: "", searched: "", failed: false });
  });

  // The server lists fifty unless asked for more, and two hundred at the most.
  it("shows as many canvases as the server lists at once, and counts the ones past that", async () => {
    for (let n = 0; n < 205; n += 1) backend.canvas.add({ title: `Canvas ${n}` });

    const { result } = await openLibrary();

    expect(LIBRARY_LIMIT).toBe(200);
    expect(result.current.items).toHaveLength(200);
    expect(result.current.usage?.count).toBe(205);
  });

  it("shows the canvases and what they hold as each arrives, neither waiting for the other", async () => {
    backend.canvas.add({ title: "Một" });
    const list = backend.canvas.holdNext("GET /artifacts", "reply");
    const { result } = await openLibrary();
    expect(result.current.items).toBeNull();
    expect(result.current.usage?.count).toBe(1);
    await release(list);
    expect(titles(result.current.items)).toEqual(["Một"]);

    const sizes = backend.canvas.holdNext("GET /artifacts/usage", "reply");
    backend.canvas.add({ title: "Hai" });
    act(() => result.current.retry());
    await landed();
    expect(titles(result.current.items)).toEqual(["Hai", "Một"]);
    expect(result.current.usage?.count).toBe(1);
    await release(sizes);
    expect(result.current.usage?.count).toBe(2);
  });

  it("shows the canvases without sizes when what they hold cannot be read", async () => {
    backend.canvas.add({ title: "Một" });
    const { result } = await openLibrary();
    expect(result.current.usage?.count).toBe(1);
    backend.canvas.refuseNext("GET /artifacts/usage", 503);

    act(() => result.current.retry());
    await landed();
    expect(result.current).toMatchObject({ usage: null, failed: false });
    expect(titles(result.current.items)).toEqual(["Một"]);

    act(() => result.current.retry());
    await landed();
    expect(result.current.usage?.count).toBe(1);
  });

  it("says the canvases could not be read, and reads them again on retry", async () => {
    backend.canvas.add({ title: "Một" });
    backend.canvas.refuseNext("GET /artifacts", 503);
    const { result } = await openLibrary();
    expect(result.current).toMatchObject({ items: null, failed: true });

    act(() => result.current.retry());
    await landed();

    expect(result.current.failed).toBe(false);
    expect(titles(result.current.items)).toEqual(["Một"]);
  });

  it("keeps the canvases it has, and the words they were found with, when reading them again fails", async () => {
    backend.canvas.add({ title: "Kế hoạch" });
    backend.canvas.add({ title: "Ghi chú" });
    const view = await openLibrary();
    await search(view, "kế");
    backend.canvas.refuseNext("GET /artifacts", 503);

    act(() => view.result.current.retry());
    await landed();

    expect(view.result.current).toMatchObject({ failed: true, searched: "kế" });
    expect(titles(view.result.current.items)).toEqual(["Kế hoạch"]);
  });
});

describe("searching the library by name", () => {
  beforeEach(() => {
    backend.canvas.add({ title: "Kế hoạch tuần", conversationIds: ["c1"] });
    backend.canvas.add({ title: "Ghi chú" });
  });

  it("waits a quarter of a second after the last key, then asks for the name as a parameter of its own", async () => {
    const { result } = await openLibrary();

    act(() => result.current.setQuery("kế"));
    expect(result.current.query).toBe("kế");
    wait(249);
    act(() => result.current.setQuery("kế h&limit=1"));
    wait(249);
    expect(lists()).toHaveLength(1);
    wait(1);
    await landed();

    expect(lists()).toHaveLength(2);
    expect(asked(lists()[1])).toEqual({ q: "kế h&limit=1", limit: String(LIBRARY_LIMIT) });
    expect(result.current).toMatchObject({ items: [], searched: "kế h&limit=1" });
  });

  it("finds the canvases whose name holds the words, and every canvas again once the box is empty", async () => {
    const view = await openLibrary();

    await search(view, "  kế hoạch ");
    expect(titles(view.result.current.items)).toEqual(["Kế hoạch tuần"]);
    expect(view.result.current).toMatchObject({ query: "  kế hoạch ", searched: "kế hoạch" });

    await search(view, "");
    expect(lists()[2]).toBe(`/artifacts?limit=${LIBRARY_LIMIT}`);
    expect(titles(view.result.current.items)).toEqual(["Ghi chú", "Kế hoạch tuần"]);
    expect(view.result.current.searched).toBe("");
  });

  it("asks for nothing when the box holds what was last searched for, spaces aside", async () => {
    const view = await openLibrary();

    await search(view, "   ");
    expect(lists()).toHaveLength(1);
    await search(view, "ghi");
    expect(lists()).toHaveLength(2);
    await search(view, " ghi ");
    expect(lists()).toHaveLength(2);
    // Typed and taken back before the wait ran out.
    act(() => view.result.current.setQuery("ghi c"));
    wait(SEARCH_WAIT_MS - 1);
    await search(view, "ghi");
    expect(lists()).toHaveLength(2);
  });

  it("drops an answer that comes back after the one asked for later", async () => {
    const view = await openLibrary();
    const older = backend.canvas.holdNext("GET /artifacts", "reply");
    const olderSizes = backend.canvas.holdNext("GET /artifacts/usage", "reply");
    await search(view, "kế");
    backend.canvas.add({ title: "Ghi chép" });
    await search(view, "ghi");
    expect(titles(view.result.current.items)).toEqual(["Ghi chép", "Ghi chú"]);

    await release(older, olderSizes);

    expect(titles(view.result.current.items)).toEqual(["Ghi chép", "Ghi chú"]);
    expect(view.result.current.searched).toBe("ghi");
    expect(view.result.current.usage?.count).toBe(3);
  });

  it("drops a failure that comes back after a later read went through", async () => {
    const fail: ((error: Error) => void)[] = [];
    const pending = () => new Promise<never>((_, reject) => fail.push(reject));
    const view = await openLibrary();
    vitest.spyOn(artifactApi, "list").mockImplementationOnce(pending);
    vitest.spyOn(artifactApi, "usage").mockImplementationOnce(pending);
    await search(view, "kế");
    await search(view, "ghi");

    await act(async () => fail.forEach((reject) => reject(new TypeError("Failed to fetch"))));

    expect(view.result.current).toMatchObject({ failed: false, searched: "ghi" });
    expect(view.result.current.usage?.count).toBe(2);
  });
});

describe("keeping the library current", () => {
  it("reads once for a burst of changes, half a second after the first", async () => {
    const one = backend.canvas.add({ title: "Một" });
    const { result } = await openLibrary();

    act(() => backend.canvas.write(one.id, "x"));
    wait(300);
    act(() => backend.canvas.write(one.id, "xy"));
    wait(LIST_RELOAD_MS - 301);
    expect(lists()).toHaveLength(1);
    wait(1);
    await landed();
    expect(lists()).toHaveLength(2);
    expect(counts()).toHaveLength(2);
    expect(result.current.items?.[0].head_version).toBe(3);
    expect(result.current.usage?.bytes).toBe(3);

    act(() => backend.canvas.write(one.id, "xyz"));
    wait(LIST_RELOAD_MS);
    expect(lists()).toHaveLength(3);
  });

  // A canvas given a source is announced with no new version, and no later time to sort by.
  it("reads again after a change that wrote no version, and keeps the order", async () => {
    const old = backend.canvas.add({ title: "Cũ" });
    backend.canvas.add({ title: "Mới" });
    const { result } = await openLibrary();
    const stored = backend.canvas.canvases.get(old.id)!;
    stored.summary = { ...stored.summary, source: "workspace:coach/plan.md" };

    act(() => emitArtifactEvent({ type: "artifact", artifact: { ...stored.summary }, conversation_ids: [] }));
    wait(LIST_RELOAD_MS);
    await landed();

    expect(titles(result.current.items)).toEqual(["Mới", "Cũ"]);
    expect(result.current.items?.[1].source).toBe("workspace:coach/plan.md");
  });

  it("reads again with the words searched for, when the stream comes back and when the tab shows", async () => {
    backend.canvas.add({ title: "Kế hoạch" });
    const view = await openLibrary();
    await search(view, "kế");

    view.rerender({ connected: false });
    view.rerender({ connected: true });
    expect(lists()).toHaveLength(3);
    setVisibility("hidden");
    expect(lists()).toHaveLength(3);
    setVisibility("visible");

    expect(lists().slice(2).map((path) => asked(path).q)).toEqual(["kế", "kế"]);
  });

  it("reads once when the stream first connects after the library is shown", async () => {
    const { rerender } = await openLibrary(false);

    rerender({ connected: true });
    await landed();

    expect(lists()).toHaveLength(1);
  });

  it("stops reading once the library is left", async () => {
    const one = backend.canvas.add({ title: "Một" });
    const { result, unmount } = await openLibrary();
    act(() => result.current.setQuery("một"));
    act(() => backend.canvas.write(one.id, "x"));

    unmount();
    wait(LIST_RELOAD_MS);
    setVisibility("visible");
    await landed();

    expect(lists()).toHaveLength(1);
  });
});
