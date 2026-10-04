import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { ArtifactSummary } from "../api/artifact-types";
import { saveInBackground } from "../lib/canvas-handoff";
import { openState } from "../lib/canvas-machine";
import { canvasTemplate } from "../lib/canvas-templates";
import { idleHandle } from "../test/canvas-dock-hook";
import { landed, startServer, stopServer, wait } from "../test/canvas-hook";
import { type LeftCanvas, leftCanvas } from "../test/canvas-left";
import type { FakeBackend } from "../test/fake-backend";
import { type CanvasDock, DOCK_FLUSH_MS, type PanelHandle, useCanvasDock } from "./use-canvas-dock";

let backend: FakeBackend;
let note: ArtifactSummary;

beforeEach(() => {
  backend = startServer();
  backend.create({ title: "Một" });
  backend.create({ title: "Hai" });
  note = backend.canvas.add({ title: "Ghi chú", conversationIds: ["c1"] });
});

afterEach(stopServer);

type Props = { conversationId: string | null };
type Seen = { conversationId: string | null; view: CanvasDock["view"]; artifactId: string | null };

/** The dock on conversation c1, with every render it made. */
async function openDock() {
  const renders: Seen[] = [];
  const view = renderHook(
    ({ conversationId }: Props) => {
      const dock = useCanvasDock(conversationId, true, true);
      renders.push({ conversationId, view: dock.view, artifactId: dock.artifactId });
      return dock;
    },
    { initialProps: { conversationId: "c1" } as Props },
  );
  await landed();
  return { ...view, renders };
}

/** An open panel whose last save answers with `answer`; it never answers by default. */
function panel(answer: Promise<number | null> = new Promise(() => {}), gone = false) {
  return { flush: vitest.fn(() => answer), gone: () => gone, typing: () => false, ...idleHandle } satisfies PanelHandle;
}

/** A promise to be settled by the test. */
function later<T>() {
  let settle!: (value: T) => void;
  const promise = new Promise<T>((resolve) => {
    settle = resolve;
  });
  return { promise, settle };
}

function opened(dock: { current: CanvasDock }, handle: PanelHandle) {
  act(() => dock.current.open("a1"));
  let unbind = () => {};
  act(() => {
    unbind = dock.current.bind(handle);
  });
  return unbind;
}

const failedSave = (title: string, over: Partial<LeftCanvas> = {}) =>
  saveInBackground(
    leftCanvas("a1", async () => null, {
      state: { ...openState("a1", null), summary: { ...note, title } },
      ...over,
    }),
  );

describe("the canvas dock across conversations", () => {
  it("never shows the last conversation's canvas in a render of the next one", async () => {
    const { result, rerender, renders } = await openDock();
    opened(result, panel());

    rerender({ conversationId: "c2" });

    expect(renders.filter((seen) => seen.conversationId === "c2")).not.toEqual([]);
    for (const seen of renders.filter((seen) => seen.conversationId === "c2")) {
      expect(seen).toMatchObject({ view: "closed", artifactId: null });
    }
  });

  it("leaves the next conversation empty when the last canvas's save fails after the switch", async () => {
    const answer = later<number | null>();
    const { result, rerender } = await openDock();
    const unbind = opened(result, panel(answer.promise));
    let closing = Promise.resolve();
    act(() => {
      closing = result.current.close();
    });

    rerender({ conversationId: "c2" });
    unbind();
    await act(async () => {
      answer.settle(null);
      await closing;
    });

    expect(result.current).toMatchObject({ view: "closed", stuck: false });
    rerender({ conversationId: "c1" });
    expect(result.current).toMatchObject({ view: "closed", artifactId: null, stuck: false });
  });
});

describe("making a canvas", () => {
  it("makes an untitled markdown canvas in this conversation and opens it with its title to edit", async () => {
    const { result } = await openDock();
    await act(() => result.current.showList());

    await act(() => result.current.create());

    expect(backend.requests.filter((request) => request.method === "POST")).toEqual([
      { method: "POST", path: "/artifacts", body: { title: "Tài liệu không tên", kind: "markdown", content: "", conversation_id: "c1" } },
    ]);
    expect(result.current).toMatchObject({ view: "canvas", artifactId: "a2", created: true, creating: false });
  });

  it.each(["code", "html", "svg", "mermaid"] as const)("makes a %s canvas holding what one of its kind starts from", async (kind) => {
    const { result } = await openDock();
    await act(() => result.current.showList());

    await act(() => result.current.create(kind));

    const body = { title: "Tài liệu không tên", kind, content: canvasTemplate(kind), conversation_id: "c1" };
    expect(backend.requests.filter((request) => request.method === "POST")).toEqual([{ method: "POST", path: "/artifacts", body }]);
    expect(backend.canvas.content("a2")).toBe(canvasTemplate(kind));
    expect(result.current).toMatchObject({ view: "canvas", artifactId: "a2", created: true, creating: false });
  });

  it("sends nothing, and shows no request as out, while no conversation is open to put the canvas in", async () => {
    const { result, rerender } = await openDock();
    rerender({ conversationId: null });
    const before = backend.requests.length;

    await act(() => result.current.create("html"));

    expect(backend.requests.slice(before)).toEqual([]);
    expect(result.current).toMatchObject({ view: "closed", artifactId: null, creating: false, createFailed: false });
    expect(backend.canvas.canvases.has("a2")).toBe(false);
  });

  it.each([
    ["the dock closes", (_: unknown, dock: { current: CanvasDock }) => act(() => dock.current.close())],
    ["another conversation opens", (rerender: (props: Props) => void) => act(async () => rerender({ conversationId: "c2" }))],
  ])("opens nothing when the reply comes after %s", async (_, move) => {
    const release = backend.canvas.holdNext("POST /artifacts", "reply");
    const { result, rerender } = await openDock();
    await act(() => result.current.showList());
    let creating = Promise.resolve();
    act(() => {
      creating = result.current.create();
    });
    expect(result.current.creating).toBe(true);

    await move(rerender, result);
    await act(async () => {
      await release();
      await creating;
    });

    expect(result.current).toMatchObject({ view: "closed", artifactId: null, creating: false });
    expect(backend.canvas.canvases.has("a2")).toBe(true);
  });

  it("says so when the canvas could not be made, and stays on the list", async () => {
    backend.canvas.refuseNext("POST /artifacts", 503);
    const { result } = await openDock();
    await act(() => result.current.showList());

    await act(() => result.current.create());

    expect(result.current).toMatchObject({ view: "list", createFailed: true, creating: false });
  });
});

describe("leaving an open canvas", () => {
  it("gives up on the open canvas's save after 5 seconds", async () => {
    const { result } = await openDock();
    opened(result, panel());
    let flushed: number | null | undefined;
    void result.current.flush().then((version) => {
      flushed = version;
    });

    wait(DOCK_FLUSH_MS - 1);
    await landed();
    expect(flushed).toBeUndefined();
    wait(1);
    await landed();

    expect(flushed).toBeNull();
  });

  it.each([
    ["close", "closed"],
    ["showList", "list"],
  ] as const)("moves on from %s once the last save lands", async (move, view) => {
    const answer = later<number | null>();
    const { result } = await openDock();
    opened(result, panel(answer.promise));
    let moving = Promise.resolve();
    act(() => {
      moving = result.current[move]();
    });
    expect(result.current.view).toBe("canvas");

    await act(async () => {
      answer.settle(2);
      await moving;
    });

    expect(result.current).toMatchObject({ view, artifactId: null, stuck: false });
  });

  it.each(["close", "showList"] as const)("stays on the canvas from %s when no save lands, until closed anyway", async (move) => {
    const { result } = await openDock();
    opened(result, panel(Promise.resolve(null)));

    await act(() => result.current[move]());
    expect(result.current).toMatchObject({ view: "canvas", artifactId: "a1", stuck: true });

    act(() => result.current.forceClose());
    expect(result.current).toMatchObject({ view: "closed", artifactId: null, stuck: false });
  });

  it("stays when the save times out", async () => {
    const { result } = await openDock();
    opened(result, panel());
    let closing = Promise.resolve();
    act(() => {
      closing = result.current.close();
    });

    wait(DOCK_FLUSH_MS);
    await act(() => closing);

    expect(result.current).toMatchObject({ view: "canvas", stuck: true });
  });

  it.each([
    ["close", "closed"],
    ["showList", "list"],
  ] as const)("moves on from %s while the last save is still inside its own deadline, which the handoff waits out", async (move, view) => {
    const { result } = await openDock();
    opened(result, { ...panel(), waitMs: () => 20_000 });
    let moving = Promise.resolve();
    act(() => {
      moving = result.current[move]();
    });

    wait(DOCK_FLUSH_MS);
    await act(() => moving);

    expect(result.current).toMatchObject({ view, artifactId: null, stuck: false });
  });

  it("stays once the deadline of the save has passed and no version holds the text", async () => {
    const { result } = await openDock();
    let left = 20_000;
    opened(result, { ...panel(), waitMs: () => left });
    let closing = Promise.resolve();
    act(() => {
      closing = result.current.close();
    });

    left = 0;
    wait(DOCK_FLUSH_MS);
    await act(() => closing);

    expect(result.current).toMatchObject({ view: "canvas", stuck: true });
  });

  it("closes a canvas deleted while its last save was out", async () => {
    const answer = later<number | null>();
    const canvas = { gone: false };
    const { result } = await openDock();
    opened(result, { flush: () => answer.promise, gone: () => canvas.gone, typing: () => false, ...idleHandle });
    let closing = Promise.resolve();
    act(() => {
      closing = result.current.close();
    });

    canvas.gone = true;
    await act(async () => {
      answer.settle(null);
      await closing;
    });

    expect(result.current).toMatchObject({ view: "closed", stuck: false });
  });

  it("closes a deleted canvas at once, without waiting for a save", async () => {
    const { result } = await openDock();
    const handle = panel(new Promise(() => {}), true);
    opened(result, handle);

    await act(() => result.current.close());

    expect(result.current.view).toBe("closed");
    expect(handle.flush).not.toHaveBeenCalled();
  });
});

describe("saves that fail after the panel went", () => {
  it("tells of each until dismissed", async () => {
    const { result } = await openDock();

    await act(() => failedSave("Ghi chú"));
    await act(() => failedSave("Ghi chú mới"));
    expect(result.current.handoffs).toEqual([{ id: "a1", title: "Ghi chú mới", draft: true }]);

    act(() => result.current.dismissHandoff("a1"));
    expect(result.current.handoffs).toEqual([]);
  });

  it("does not tell of a canvas the person closed anyway, and tells of the next failure again", async () => {
    const { result } = await openDock();
    opened(result, panel(Promise.resolve(null)));
    await act(() => result.current.close());
    act(() => result.current.forceClose());

    await act(() => failedSave("Ghi chú"));
    expect(result.current.handoffs).toEqual([]);

    await act(() => failedSave("Ghi chú"));
    expect(result.current.handoffs).toEqual([{ id: "a1", title: "Ghi chú", draft: true }]);
  });
});

describe("a canvas closed anyway, by what this device kept", () => {
  it("is told of by the notice when this device could not keep its text, which is all the person gets", async () => {
    const { result } = await openDock();
    opened(result, { ...panel(Promise.resolve(null)), draftFailed: () => true });
    await act(() => result.current.close());
    act(() => result.current.forceClose());

    await act(() => failedSave("Ghi chú", { draftFailed: true }));

    expect(result.current.handoffs).toEqual([{ id: "a1", title: "Ghi chú", draft: false }]);
  });

  it("is not told of when this device kept its text, the person having been told already", async () => {
    const { result } = await openDock();
    opened(result, { ...panel(Promise.resolve(null)), draftFailed: () => false });
    await act(() => result.current.close());
    act(() => result.current.forceClose());

    await act(() => failedSave("Ghi chú"));

    expect(result.current.handoffs).toEqual([]);
  });
});

describe("the tabs beside a wide conversation", () => {
  it("brings the canvas forward on each opening, and the button toggles the dock", async () => {
    const { result } = await openDock();
    act(() => result.current.open("a1"));
    expect(result.current.tab).toBe("canvas");

    act(() => result.current.selectTab("activity"));
    expect(result.current.tab).toBe("activity");
    await act(() => result.current.toggle());
    expect(result.current).toMatchObject({ view: "canvas", tab: "canvas" });

    await act(() => result.current.toggle());
    expect(result.current.view).toBe("closed");
    await act(() => result.current.toggle());
    expect(result.current).toMatchObject({ view: "list", tab: "canvas" });
  });
});
