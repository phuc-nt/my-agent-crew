import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { readDraft } from "../lib/canvas-draft";
import { DRAFT_DELAY_MS } from "../lib/canvas-runner";
import { landed, openCanvas, sent, setVisibility, startServer, stopServer, wait } from "../test/canvas-hook";
import type { FakeBackend } from "../test/fake-backend";
import { refusingStorage } from "../test/memory-storage";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
  backend.canvas.add({ content: "a" });
  backend.canvas.add({ content: "b" });
});

afterEach(stopServer);

describe("moving to another canvas", () => {
  it("shows the next canvas at once and finishes the last one's save behind it", async () => {
    const { result, rerender } = await openCanvas();
    act(() => result.current.edit("a!"));
    wait(100);

    rerender({ id: "a2", connected: true });

    expect(result.current.state).toMatchObject({ id: "a2", phase: "loading", text: "" });
    expect(readDraft("a1")?.text).toBe("a!");
    expect(sent(backend, "PUT", "a1")).toHaveLength(1);
    await landed();
    expect(result.current.state).toMatchObject({ id: "a2", phase: "ready", text: "b" });
    expect(backend.canvas.content("a1")).toBe("a!");
    expect(readDraft("a1")).toBeNull();
  });

  it("tries a waiting retry once more on leaving, then keeps the draft and stops", async () => {
    const { result, rerender } = await openCanvas();
    backend.canvas.refuseNext("PUT", 503);
    backend.canvas.refuseNext("PUT", 503);
    act(() => result.current.edit("a!"));
    wait(1500);
    await landed();
    expect(result.current.status).toBe("serverDown");

    rerender({ id: "a2", connected: true });
    await landed();
    wait(60_000);
    await landed();

    expect(sent(backend, "PUT", "a1")).toHaveLength(2);
    expect(readDraft("a1")?.text).toBe("a!");
  });

  it("saves nothing for the next canvas when the tab hides while it loads, and the last one once", async () => {
    const { result, rerender } = await openCanvas();
    act(() => result.current.edit("a!"));

    rerender({ id: "a2", connected: true });
    setVisibility("hidden");

    expect(sent(backend, "PUT", "a1")).toHaveLength(1);
    await landed();
    expect(sent(backend, "PUT", "a1")).toHaveLength(1);
    expect(sent(backend, "PUT", "a2")).toEqual([]);
    expect(readDraft("a2")).toBeNull();
    expect(backend.canvas.content("a1")).toBe("a!");
  });

  it("lets a canvas left behind finish its save without reading it again or showing it", async () => {
    const { result, rerender } = await openCanvas();
    const release = backend.canvas.holdNext("PUT", "reply");
    act(() => result.current.edit("a!"));
    act(() => result.current.save());
    // Someone writes while the save is out, which an open panel would read once the save lands.
    act(() => backend.canvas.write("a1", "a!\nc"));

    rerender({ id: "a2", connected: true });
    await landed();
    await act(() => release());
    await landed();

    expect(result.current.state).toMatchObject({ id: "a2", phase: "ready", text: "b" });
    expect(sent(backend, "GET", "a1")).toHaveLength(1);
    expect(readDraft("a1")).toBeNull();
  });

  it("does not carry the warning about a draft this device could not keep", async () => {
    refusingStorage();
    const { result, rerender } = await openCanvas();
    act(() => result.current.edit("a!"));
    wait(DRAFT_DELAY_MS);
    expect(result.current.draftFailed).toBe(true);

    rerender({ id: "a2", connected: true });

    expect(result.current.draftFailed).toBe(false);
  });
});
