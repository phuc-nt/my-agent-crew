import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { NOTE, SHOP } from "../test/canvas-dock-hook";
import { landed, sent, startServer, stopServer } from "../test/canvas-hook";
import type { FakeBackend } from "../test/fake-backend";
import { useCanvasConversations } from "./use-canvas-conversations";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
  backend.canvas.add({ id: NOTE, title: "Ghi chú", content: "a", conversationIds: ["c2", "c1"] });
  backend.canvas.add({ id: SHOP, title: "Mua sắm", content: "b", conversationIds: ["c3"] });
});

afterEach(stopServer);

async function used(id = NOTE) {
  const view = renderHook((p: { id: string }) => useCanvasConversations(p.id), { initialProps: { id } });
  await landed();
  return view;
}

const reads = (id = NOTE) => sent(backend, "GET", id).length;
const linked = (id = NOTE) => backend.canvas.canvases.get(id)?.conversationIds as string[];
const hold = (id = NOTE) => backend.canvas.holdNext(`GET /artifacts/${id}`, "reply");
/** The stream's word that the canvas changed, as a save by someone else would bring it. */
const changed = (id = NOTE) => act(() => void backend.canvas.write(id, "khác"));

/** Lets a held reply through. */
async function release(gate: () => Promise<void>) {
  await act(() => gate());
  await landed();
}

describe("the conversations a canvas is used in", () => {
  it("are read once, in the order the server gives them, and none is named before that", async () => {
    const gate = hold();
    const { result } = await used();
    expect(result.current).toEqual([]);

    await release(gate);

    expect(result.current).toEqual(["c2", "c1"]);
    expect(reads()).toBe(1);
  });

  it("are none when the read fails", async () => {
    backend.canvas.refuseNext(`GET /artifacts/${NOTE}`, 503);

    const { result } = await used();

    expect(result.current).toEqual([]);
    expect(reads()).toBe(1);
  });

  it("are read again when the stream says the canvas changed, and not for news of another canvas", async () => {
    const { result } = await used();
    linked().push("c9");

    changed(SHOP);
    await landed();
    expect(reads()).toBe(1);
    expect(result.current).toEqual(["c2", "c1"]);

    changed();
    await landed();
    expect(reads()).toBe(2);
    expect(result.current).toEqual(["c2", "c1", "c9"]);
  });

  it("are none again when a later read fails: what was read before may no longer be true", async () => {
    const { result } = await used();
    expect(result.current).toEqual(["c2", "c1"]);

    backend.canvas.refuseNext(`GET /artifacts/${NOTE}`, 503);
    changed();
    await landed();

    expect(result.current).toEqual([]);
  });

  it("are none once the canvas is deleted, with nothing asked and a read still out dropped", async () => {
    const { result } = await used();
    const late = hold();
    changed();
    expect(reads()).toBe(2);

    act(() => backend.canvas.remove(NOTE));
    expect(result.current).toEqual([]);
    expect(reads()).toBe(2);

    await release(late);
    expect(result.current).toEqual([]);
  });

  it("keep the newest answer when an older one comes after it", async () => {
    const { result } = await used();
    const late = hold();
    changed();
    linked().push("c9");
    changed();
    await landed();
    expect(result.current).toEqual(["c2", "c1", "c9"]);

    // The first of the two reads is answered last, with what was true when it was asked.
    await release(late);

    expect(reads()).toBe(3);
    expect(result.current).toEqual(["c2", "c1", "c9"]);
  });

  it("are those of the canvas named now: none until its read lands, and an answer about the last one is dropped", async () => {
    const { result, rerender } = await used();
    const late = hold();
    changed();
    const next = hold(SHOP);

    rerender({ id: SHOP });
    expect(result.current).toEqual([]);
    await release(late);
    expect(result.current).toEqual([]);

    await release(next);
    expect(result.current).toEqual(["c3"]);

    // The canvas left is listened to no longer.
    changed(NOTE);
    await landed();
    expect(reads(NOTE)).toBe(2);
  });

  it("are asked about no more once the page is gone", async () => {
    const { unmount } = await used();

    unmount();
    changed();
    await landed();

    expect(reads()).toBe(1);
  });
});
