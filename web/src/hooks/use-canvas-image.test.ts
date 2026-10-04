import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { readDraft } from "../lib/canvas-draft";
import { landed, openCanvas, sent, startServer, stopServer, wait } from "../test/canvas-hook";
import type { FakeBackend } from "../test/fake-backend";
import { SAMPLES } from "../test/fake-canvas-kinds";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
  backend.canvas.add({ ...SAMPLES.image, agent_id: "ming" });
});

afterEach(stopServer);

/** Every request the tab made that would change something on the server. */
const writes = () => backend.requests.filter((request) => request.method !== "GET");

describe("a canvas that is a picture, whose detail holds no text", () => {
  it("opens as read and saved, with an empty text that nothing is ever sent of", async () => {
    const { result } = await openCanvas();

    expect(result.current.state).toMatchObject({ phase: "ready", text: "", gone: false, conflict: null });
    expect(result.current.state.base).toMatchObject({ version: 1, content: "", author: "agent:ming" });
    expect(result.current.status).toBe("saved");

    wait(10 * 60_000);
    await landed();

    expect(sent(backend, "GET")).toHaveLength(1);
    expect(writes()).toEqual([]);
    expect(readDraft("a1")).toBeNull();
  });

  it("reads a new picture once when the stream tells of it, and only moves to its version", async () => {
    const { result } = await openCanvas();

    act(() => {
      backend.canvas.write("a1", null, { author: "agent:ming" });
    });
    expect(sent(backend, "GET")).toHaveLength(2);
    await landed();
    wait(10 * 60_000);
    await landed();

    expect(sent(backend, "GET")).toHaveLength(2);
    expect(writes()).toEqual([]);
    expect(result.current.state).toMatchObject({ phase: "ready", text: "", conflict: null });
    expect(result.current.state.base).toMatchObject({ version: 2, content: "" });
    expect(result.current.status).toBe("saved");
  });

  it("takes a restored picture as the newest version, still with no text and nothing to save", async () => {
    const { result } = await openCanvas();

    act(() => result.current.restored(2, null));
    wait(10 * 60_000);
    await landed();

    expect(result.current.state).toMatchObject({ phase: "ready", text: "", conflict: null });
    expect(result.current.state.base).toMatchObject({ version: 2, content: "" });
    expect(result.current.status).toBe("saved");
    expect(writes()).toEqual([]);
  });
});
