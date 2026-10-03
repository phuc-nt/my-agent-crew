import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { artifactApi } from "../api/artifact-client";
import type { ArtifactEvent } from "../api/artifact-types";
import { onArtifactEvent } from "../lib/artifact-events";
import { landed, startServer, stopServer } from "../test/canvas-hook";
import type { FakeBackend } from "../test/fake-backend";
import { useCanvasList } from "./use-canvas-list";

const NOTE = "0123456789ab";
const SHOP = "ba9876543210";

let backend: FakeBackend;
let heard: ArtifactEvent[];
let unsubscribe: () => void;

beforeEach(() => {
  backend = startServer();
  heard = [];
  unsubscribe = onArtifactEvent((event) => heard.push(event));
});

afterEach(() => {
  unsubscribe();
  stopServer();
});

type Props = { conversationId: string | null };

async function openList(props: Props = { conversationId: "c1" }) {
  const view = renderHook((p: Props) => useCanvasList(p.conversationId, true), { initialProps: props });
  await landed();
  return view;
}

const canvasReads = (id: string) =>
  backend.requests.filter((request) => request.method === "GET" && request.path === `/artifacts/${id}`);
const lists = () => backend.requests.filter((request) => request.path.startsWith("/artifacts?"));
const deletions = () => heard.filter((event) => "deleted" in event.artifact);

describe("the title of a canvas a card names", () => {
  it("is the title the list holds, and asks the server nothing more", async () => {
    backend.canvas.add({ id: NOTE, title: "Ghi chú", conversationIds: ["c1"] });
    const { result } = await openList();

    act(() => result.current.verify(NOTE));
    await landed();

    expect(result.current.titleOf(NOTE)).toBe("Ghi chú");
    expect(canvasReads(NOTE)).toEqual([]);
  });

  it("is not known for a canvas nobody has read", async () => {
    backend.canvas.add({ id: SHOP, title: "Mua sắm", conversationIds: ["c2"] });
    const { result } = await openList();

    expect(result.current.titleOf(SHOP)).toBeNull();
    expect(result.current.isGone(SHOP)).toBe(false);
  });

  it("comes from a read of a canvas the list does not hold, once and for good", async () => {
    backend.canvas.add({ id: SHOP, title: "Mua sắm", conversationIds: ["c2"] });
    const { result } = await openList();

    act(() => result.current.verify(SHOP));
    await landed();
    act(() => result.current.retry());
    await landed();
    act(() => result.current.verify(SHOP));
    await landed();

    expect(result.current.titleOf(SHOP)).toBe("Mua sắm");
    expect(result.current.isGone(SHOP)).toBe(false);
    expect(canvasReads(SHOP)).toHaveLength(1);
  });

  it("goes to the list's title once the list holds the canvas", async () => {
    const { result } = await openList();
    act(() => backend.canvas.add({ id: SHOP, title: "Mua sắm", conversationIds: [] }));
    act(() => result.current.verify(SHOP));
    await landed();
    expect(result.current.titleOf(SHOP)).toBe("Mua sắm");

    backend.canvas.canvases.get(SHOP)?.conversationIds.push("c1");
    await act(() => artifactApi.rename(SHOP, "Mua sắm tuần này"));
    act(() => result.current.retry());
    await landed();

    expect(result.current.titleOf(SHOP)).toBe("Mua sắm tuần này");
  });
});

describe("asking whether a canvas is still there", () => {
  it("waits for the list to be read, so a canvas it holds is never asked about", async () => {
    backend.canvas.add({ id: NOTE, title: "Ghi chú", conversationIds: ["c1"] });
    const release = backend.canvas.holdNext("GET /artifacts", "reply");
    const { result } = await openList();

    act(() => result.current.verify(NOTE));
    await landed();
    expect(canvasReads(NOTE)).toEqual([]);
    await act(() => release());
    await landed();

    expect(canvasReads(NOTE)).toEqual([]);
    expect(result.current.titleOf(NOTE)).toBe("Ghi chú");
  });

  it("asks once the list is in when it does not hold the canvas", async () => {
    backend.canvas.add({ id: SHOP, title: "Mua sắm", conversationIds: ["c2"] });
    const release = backend.canvas.holdNext("GET /artifacts", "reply");
    const { result } = await openList();
    act(() => result.current.verify(SHOP));
    await landed();
    expect(canvasReads(SHOP)).toEqual([]);

    await act(() => release());
    await landed();

    expect(canvasReads(SHOP)).toHaveLength(1);
    expect(result.current.titleOf(SHOP)).toBe("Mua sắm");
  });

  it("asks again after each read of the list while the answer is not settled", async () => {
    backend.canvas.add({ id: SHOP, title: "Mua sắm", conversationIds: ["c2"] });
    backend.canvas.refuseNext(`GET /artifacts/${SHOP}`, 503);
    const { result } = await openList();

    act(() => result.current.verify(SHOP));
    await landed();
    expect(canvasReads(SHOP)).toHaveLength(1);
    expect(result.current.titleOf(SHOP)).toBeNull();
    expect(deletions()).toEqual([]);
    act(() => result.current.retry());
    await landed();

    expect(canvasReads(SHOP)).toHaveLength(2);
    expect(result.current.titleOf(SHOP)).toBe("Mua sắm");
  });

  it("takes a lost connection as no answer, and asks again after the next read", async () => {
    backend.canvas.add({ id: SHOP, title: "Mua sắm", conversationIds: ["c2"] });
    const get = vitest.spyOn(artifactApi, "get").mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const { result } = await openList();

    act(() => result.current.verify(SHOP));
    await landed();
    expect(deletions()).toEqual([]);
    expect(result.current.isGone(SHOP)).toBe(false);
    act(() => result.current.retry());
    await landed();

    expect(get).toHaveBeenCalledTimes(2);
    expect(result.current.titleOf(SHOP)).toBe("Mua sắm");
  });

  it("takes a 404 as the canvas being deleted and tells every listener once", async () => {
    const { result } = await openList();

    act(() => result.current.verify(SHOP));
    await landed();

    expect(deletions()).toEqual([{ type: "artifact", artifact: { id: SHOP, deleted: true }, conversation_ids: [] }]);
    expect(result.current.isGone(SHOP)).toBe(true);
    act(() => result.current.retry());
    await landed();
    act(() => result.current.verify(SHOP));
    await landed();
    expect(canvasReads(SHOP)).toHaveLength(1);
    expect(deletions()).toHaveLength(1);
  });

  it("does not take any other refusal for a deletion", async () => {
    backend.canvas.add({ id: SHOP, title: "Mua sắm", conversationIds: ["c2"] });
    for (const status of [400, 401, 403, 409, 500, 502]) backend.canvas.refuseNext(`GET /artifacts/${SHOP}`, status);
    const { result } = await openList();

    for (let tries = 0; tries < 6; tries++) {
      act(() => result.current.verify(SHOP));
      await landed();
      act(() => result.current.retry());
      await landed();
    }

    expect(deletions()).toEqual([]);
    expect(result.current.isGone(SHOP)).toBe(false);
    expect(result.current.titleOf(SHOP)).toBe("Mua sắm");
  });

  it("has one read out at a time for a canvas", async () => {
    backend.canvas.add({ id: SHOP, title: "Mua sắm", conversationIds: ["c2"] });
    const release = backend.canvas.holdNext(`GET /artifacts/${SHOP}`, "reply");
    const { result } = await openList();

    act(() => result.current.verify(SHOP));
    act(() => result.current.verify(SHOP));
    act(() => result.current.retry());
    await landed();
    expect(canvasReads(SHOP)).toHaveLength(1);
    await act(() => release());
    await landed();

    expect(canvasReads(SHOP)).toHaveLength(1);
    expect(result.current.titleOf(SHOP)).toBe("Mua sắm");
  });

  it("asks about no id the server does not make", async () => {
    const { result } = await openList();
    const before = backend.requests.length;

    for (const id of ["..", "../x", "a1", "", "0123456789AB", `${NOTE}/versions`]) {
      act(() => result.current.verify(id));
    }
    await landed();
    act(() => result.current.retry());
    await landed();

    expect(backend.requests.slice(before).filter((request) => !request.path.startsWith("/artifacts?"))).toEqual([]);
    expect(result.current.titleOf("..")).toBeNull();
  });

  it("forgets what it was to ask about when another conversation opens", async () => {
    backend.canvas.add({ id: SHOP, title: "Mua sắm", conversationIds: ["c2"] });
    const release = backend.canvas.holdNext("GET /artifacts", "reply");
    const { result, rerender } = await openList();
    act(() => result.current.verify(SHOP));

    rerender({ conversationId: "c3" });
    await landed();
    await act(() => release());
    await landed();

    expect(lists()).toHaveLength(2);
    expect(canvasReads(SHOP)).toEqual([]);
  });

  it("is the same function after the list is read and when the conversation changes", async () => {
    const { result, rerender } = await openList();
    const verify = result.current.verify;

    act(() => result.current.retry());
    await landed();
    rerender({ conversationId: "c2" });
    await landed();

    expect(result.current.verify).toBe(verify);
  });
});

describe("a canvas deleted", () => {
  it("is heard from the stream", async () => {
    backend.canvas.add({ id: NOTE, title: "Ghi chú", conversationIds: ["c1"] });
    const { result } = await openList();
    expect(result.current.isGone(NOTE)).toBe(false);

    act(() => backend.canvas.remove(NOTE));

    expect(result.current.isGone(NOTE)).toBe(true);
    expect(result.current.isGone(SHOP)).toBe(false);
  });

  it("is still gone after the list is read without it", async () => {
    backend.canvas.add({ id: NOTE, title: "Ghi chú", conversationIds: ["c1"] });
    const { result } = await openList();
    act(() => backend.canvas.remove(NOTE));

    act(() => result.current.retry());
    await landed();

    expect(result.current.items).toEqual([]);
    expect(result.current.isGone(NOTE)).toBe(true);
  });

  it("is not the same as a canvas changed", async () => {
    backend.canvas.add({ id: NOTE, title: "Ghi chú", conversationIds: ["c1"] });
    const { result } = await openList();

    act(() => backend.canvas.write(NOTE, "mới"));

    expect(result.current.isGone(NOTE)).toBe(false);
  });
});
