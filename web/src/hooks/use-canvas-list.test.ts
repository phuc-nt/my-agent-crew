import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { artifactApi } from "../api/artifact-client";
import { landed, setVisibility, startServer, stopServer, wait } from "../test/canvas-hook";
import type { FakeBackend } from "../test/fake-backend";
import { LIST_RELOAD_MS, useCanvasList } from "./use-canvas-list";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
});

afterEach(stopServer);

type Props = { conversationId: string | null; connected: boolean };

async function openList(props: Partial<Props> = {}) {
  const view = renderHook((p: Props) => useCanvasList(p.conversationId, p.connected), {
    initialProps: { conversationId: "c1", connected: true, ...props },
  });
  await landed();
  return view;
}

const reads = () => backend.requests.filter((request) => request.method === "GET" && request.path.startsWith("/artifacts?"));
const titles = (items: { title: string }[] | null) => items?.map((item) => item.title) ?? null;

describe("the canvases of the open conversation", () => {
  it("asks for nothing while no conversation is open", async () => {
    const { result } = await openList({ conversationId: null });

    expect(result.current.items).toBeNull();
    expect(reads()).toEqual([]);
  });

  it("lists only this conversation's canvases, the newest first", async () => {
    backend.canvas.add({ title: "Cũ", conversationIds: ["c1"] });
    backend.canvas.add({ title: "Của hội thoại khác", conversationIds: ["c2"] });
    backend.canvas.add({ title: "Mới", conversationIds: ["c1"] });

    const { result } = await openList();

    expect(titles(result.current.items)).toEqual(["Mới", "Cũ"]);
  });

  it("drops the last conversation's list at once, and its reply when it comes late", async () => {
    backend.canvas.add({ title: "Của c1", conversationIds: ["c1"] });
    backend.canvas.add({ title: "Của c2", conversationIds: ["c2"] });
    const release = backend.canvas.holdNext("GET /artifacts", "reply");
    const { result, rerender } = await openList();

    rerender({ conversationId: "c2", connected: true });
    expect(result.current.items).toBeNull();
    await landed();
    await act(() => release());
    await landed();

    expect(titles(result.current.items)).toEqual(["Của c2"]);
  });

  it("reads the list once for a burst of changes, half a second after the first", async () => {
    const one = backend.canvas.add({ title: "Một", conversationIds: ["c1"] });
    await openList();

    act(() => backend.canvas.write(one.id, "x"));
    wait(300);
    act(() => backend.canvas.write(one.id, "xy"));
    wait(LIST_RELOAD_MS - 301);
    expect(reads()).toHaveLength(1);
    wait(1);
    expect(reads()).toHaveLength(2);

    act(() => backend.canvas.write(one.id, "xyz"));
    wait(LIST_RELOAD_MS);
    expect(reads()).toHaveLength(3);
  });

  it("finds a canvas made elsewhere, whose announcement names no conversation yet", async () => {
    backend.create({ title: "Rộng" });
    const { result } = await openList();
    expect(result.current.items).toEqual([]);

    await act(() => artifactApi.create({ title: "Từ tab khác", kind: "markdown", conversation_id: "c1" }));
    wait(LIST_RELOAD_MS);
    await landed();

    expect(titles(result.current.items)).toEqual(["Từ tab khác"]);
  });

  it("says the list could not be read, and reads it again on retry", async () => {
    backend.canvas.add({ title: "Một", conversationIds: ["c1"] });
    backend.canvas.refuseNext("GET /artifacts", 503);
    const { result } = await openList();
    expect(result.current).toMatchObject({ items: null, failed: true });

    act(() => result.current.retry());
    await landed();

    expect(result.current.failed).toBe(false);
    expect(titles(result.current.items)).toEqual(["Một"]);
  });

  it("keeps the list it has when reading it again fails", async () => {
    backend.canvas.add({ title: "Một", conversationIds: ["c1"] });
    const { result } = await openList();
    backend.canvas.refuseNext("GET /artifacts", 503);

    act(() => result.current.retry());
    await landed();

    expect(result.current.failed).toBe(true);
    expect(titles(result.current.items)).toEqual(["Một"]);
  });

  it("reads the list again when the stream comes back and when the tab shows again", async () => {
    const { rerender } = await openList();

    rerender({ conversationId: "c1", connected: false });
    rerender({ conversationId: "c1", connected: true });
    await landed();
    expect(reads()).toHaveLength(2);

    setVisibility("hidden");
    expect(reads()).toHaveLength(2);
    setVisibility("visible");
    await landed();
    expect(reads()).toHaveLength(3);
  });

  it("hears no change once the conversation is closed", async () => {
    const one = backend.canvas.add({ title: "Một", conversationIds: ["c1"] });
    const { rerender } = await openList();

    rerender({ conversationId: null, connected: true });
    act(() => backend.canvas.write(one.id, "x"));
    wait(LIST_RELOAD_MS);

    expect(reads()).toHaveLength(1);
  });
});
