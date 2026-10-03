import { act, renderHook } from "@testing-library/react";
import type { StrictMode } from "react";
import { vi as vitest } from "vitest";
import { type CanvasDock, type PanelHandle, useCanvasDock } from "../hooks/use-canvas-dock";
import { useCanvasFocus } from "../hooks/use-canvas-focus";
import { landed, startServer } from "./canvas-hook";
import type { FakeBackend } from "./fake-backend";

/** Canvas ids as the server makes them: twelve hex digits. */
export const NOTE = "0123456789ab";
export const SHOP = "ba9876543210";

export type DockProps = { conversationId: string | null; wide: boolean };

/** A fresh server with two conversations, and two canvases shared with the first. */
export function startDockServer(): FakeBackend {
  const backend = startServer();
  backend.create({ title: "Một" });
  backend.create({ title: "Hai" });
  backend.canvas.add({ id: NOTE, title: "Ghi chú", conversationIds: ["c1"] });
  backend.canvas.add({ id: SHOP, title: "Mua sắm", conversationIds: ["c1"] });
  return backend;
}

/** The dock alone, on conversation c1, once its first read has landed. */
export async function openDock(wide = true) {
  const view = renderHook(({ conversationId, wide }: DockProps) => useCanvasDock(conversationId, true, wide), {
    initialProps: { conversationId: "c1", wide } as DockProps,
  });
  await landed();
  return view;
}

/** The dock and the focus together, in the order the chat screen mounts them: the dock counts a
 *  move before the focus reads it. */
export async function openTab(props: Partial<DockProps> = {}, wrapper?: typeof StrictMode) {
  const view = renderHook(
    ({ conversationId, wide }: DockProps) => {
      const dock = useCanvasDock(conversationId, true, wide);
      useCanvasFocus(conversationId, wide, dock);
      return dock;
    },
    { initialProps: { conversationId: "c1", wide: true, ...props }, wrapper },
  );
  await landed();
  return view;
}

/** What a panel says of its save in flight and its draft when a test does not care: no save is out
 *  and this device kept the draft. A test that does spreads its own over it. */
export const idleHandle = { waitMs: () => 0, draftFailed: () => false } satisfies Pick<
  PanelHandle,
  "waitMs" | "draftFailed"
>;

/** An open panel whose last save answers with `answer`, which it never does by default, and whose
 *  person is typing when `typing` says so, which is never by default. */
export const panel = (answer: Promise<number | null> = new Promise(() => {}), typing: () => boolean = () => false) =>
  ({ flush: vitest.fn(() => answer), gone: () => false, typing, ...idleHandle }) satisfies PanelHandle;

/** Opens canvas `id` in the dock, and lends it `handle` as the panel showing it when there is one. */
export function opened(dock: { current: CanvasDock }, id = NOTE, handle?: PanelHandle) {
  act(() => dock.current.open(id));
  if (handle) {
    act(() => {
      dock.current.bind(handle);
    });
  }
}

/** The path of a conversation's canvas route, which fault targets name. */
export const focusRoute = (id = "c1") => `/conversations/${id}/canvas`;

/** The requests the tab sent to a conversation's canvas route with `method`, oldest first. */
export const focusCalls = (backend: FakeBackend, method: "GET" | "PUT", id = "c1") =>
  backend.requests.filter((request) => request.method === method && request.path === focusRoute(id));
