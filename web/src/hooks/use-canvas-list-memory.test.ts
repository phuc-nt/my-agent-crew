import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { landed, startServer, stopServer } from "../test/canvas-hook";
import type { FakeBackend } from "../test/fake-backend";
import { useCanvasList } from "./use-canvas-list";

const NOTE = "0123456789ab";
const SHOP = "ba9876543210";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
});

afterEach(() => {
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

describe("what the list remembers of the canvases cards name", () => {
  it("keeps the title of every canvas read, not only of the last", async () => {
    backend.canvas.add({ id: NOTE, title: "Ghi chú", conversationIds: ["c2"] });
    backend.canvas.add({ id: SHOP, title: "Mua sắm", conversationIds: ["c2"] });
    const { result } = await openList();

    act(() => result.current.verify(NOTE));
    await landed();
    act(() => result.current.verify(SHOP));
    await landed();

    expect(result.current.titleOf(NOTE)).toBe("Ghi chú");
    expect(result.current.titleOf(SHOP)).toBe("Mua sắm");
  });

  it("keeps every canvas deleted, not only the last", async () => {
    backend.canvas.add({ id: NOTE, title: "Ghi chú", conversationIds: ["c1"] });
    backend.canvas.add({ id: SHOP, title: "Mua sắm", conversationIds: ["c1"] });
    const { result } = await openList();

    act(() => backend.canvas.remove(NOTE));
    act(() => backend.canvas.remove(SHOP));

    expect(result.current.isGone(NOTE)).toBe(true);
    expect(result.current.isGone(SHOP)).toBe(true);
  });

  it("waits for the list of a conversation just opened, and does not take the last one's for it", async () => {
    backend.canvas.add({ id: SHOP, title: "Mua sắm", conversationIds: ["c2"] });
    const { result, rerender } = await openList();
    const release = backend.canvas.holdNext("GET /artifacts", "reply");

    rerender({ conversationId: "c3" });
    act(() => result.current.verify(SHOP));
    await landed();
    expect(canvasReads(SHOP)).toEqual([]);
    await act(() => release());
    await landed();

    expect(canvasReads(SHOP)).toHaveLength(1);
    expect(result.current.titleOf(SHOP)).toBe("Mua sắm");
  });
});
