import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { ArtifactSummary } from "../api/artifact-types";
import { saveInBackground } from "../lib/canvas-handoff";
import { openState } from "../lib/canvas-machine";
import { landed, startServer, stopServer } from "../test/canvas-hook";
import type { FakeBackend } from "../test/fake-backend";
import { type PanelHandle, useCanvasDock } from "./use-canvas-dock";

let backend: FakeBackend;
let note: ArtifactSummary;

beforeEach(() => {
  backend = startServer();
  backend.create({ title: "Một" });
  note = backend.canvas.add({ title: "Ghi chú", conversationIds: ["c1"] });
});

afterEach(stopServer);

async function openDock(conversationId: string | null = "c1") {
  const view = renderHook(() => useCanvasDock(conversationId, true));
  await landed();
  return view;
}

/** An open panel whose last save answers `version`. */
const panel = (version: number) => ({ flush: vitest.fn(async () => version), gone: () => false }) satisfies PanelHandle;

const posts = () => backend.requests.filter((request) => request.method === "POST");

describe("the canvas tab", () => {
  it("comes forward when a canvas or the list opens over the activity", async () => {
    const { result } = await openDock();
    await act(() => result.current.showList());
    act(() => result.current.selectTab("activity"));

    act(() => result.current.open(note.id));
    expect(result.current).toMatchObject({ view: "canvas", tab: "canvas" });

    act(() => result.current.selectTab("activity"));
    await act(() => result.current.showList());
    expect(result.current).toMatchObject({ view: "list", tab: "canvas" });
  });
});

describe("making a canvas from the dock", () => {
  it("makes none while no conversation is open", async () => {
    const { result } = await openDock(null);

    await act(() => result.current.create());

    expect(posts()).toEqual([]);
    expect(result.current).toMatchObject({ view: "closed", creating: false, createFailed: false });
  });

  it("tells no failure of a canvas asked for before the person opened another one", async () => {
    const { result } = await openDock();
    await act(() => result.current.showList());
    backend.canvas.refuseNext("POST /artifacts", 503);

    await act(async () => {
      const making = result.current.create();
      result.current.open(note.id);
      await making;
    });

    expect(result.current).toMatchObject({ view: "canvas", artifactId: note.id, creating: false, createFailed: false });
  });
});

describe("a canvas closed anyway", () => {
  it("is told of again once it was opened again and its last save failed", async () => {
    const { result } = await openDock();
    act(() => result.current.open(note.id));
    act(() => result.current.forceClose());
    act(() => result.current.open(note.id));

    await act(() =>
      saveInBackground({ id: note.id, state: { ...openState(note.id, null), summary: note }, flush: async () => null }),
    );

    expect(result.current.handoffs).toEqual([{ id: note.id, title: "Ghi chú" }]);
  });
});

describe("the open panel's handle", () => {
  it("stays the newer panel's when the panel it replaced lets go late", async () => {
    const { result } = await openDock();
    const older = panel(3);
    const newer = panel(4);
    let letGo = () => {};
    act(() => {
      letGo = result.current.bind(older);
      result.current.bind(newer);
    });

    letGo();

    await expect(result.current.flush()).resolves.toBe(4);
    expect(older.flush).not.toHaveBeenCalled();
  });
});
