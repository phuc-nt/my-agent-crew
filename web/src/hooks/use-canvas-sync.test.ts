import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { readDraft, writeDraft } from "../lib/canvas-draft";
import { landed, openCanvas, sent, setVisibility, startServer, stopServer, wait } from "../test/canvas-hook";
import type { FakeBackend } from "../test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
});

afterEach(stopServer);

describe("keeping an open canvas up with the server", () => {
  it("reads it again when the stream comes back after a drop, and not when it first connects", async () => {
    backend.canvas.add({ content: "a" });
    const { rerender } = await openCanvas({ connected: false });
    expect(sent(backend, "GET")).toHaveLength(1);

    rerender({ id: "a1", connected: true });
    await landed();
    expect(sent(backend, "GET")).toHaveLength(1);

    rerender({ id: "a1", connected: false });
    rerender({ id: "a1", connected: true });
    await landed();
    expect(sent(backend, "GET")).toHaveLength(2);
  });

  it("reads it again when the tab shows, taking a write the stream never told of", async () => {
    backend.canvas.add({ content: "a" });
    const { result } = await openCanvas();
    backend.canvas.onEvent = null;
    backend.canvas.write("a1", "a\nb");

    setVisibility("hidden");
    expect(sent(backend, "GET")).toHaveLength(1);
    setVisibility("visible");
    expect(sent(backend, "GET")).toHaveLength(2);
    await landed();

    expect(result.current.state.text).toBe("a\nb");
    expect(sent(backend, "PUT")).toEqual([]);
  });

  it("reads a version the stream announces while the person is not typing", async () => {
    backend.canvas.add({ content: "a" });
    const { result } = await openCanvas();

    act(() => {
      backend.canvas.write("a1", "a\nb");
    });
    expect(sent(backend, "GET")).toHaveLength(2);
    await landed();

    expect(result.current.state.text).toBe("a\nb");
    expect(result.current.status).toBe("saved");
  });

  it("takes a save with no reply in 30 s as lost, and sends it again", async () => {
    backend.canvas.add({ content: "a" });
    const { result } = await openCanvas();
    backend.canvas.holdNext("PUT", "request");
    act(() => result.current.edit("ab"));
    wait(1500);
    expect(sent(backend, "PUT")).toHaveLength(1);

    wait(29_999);
    await landed();
    expect(result.current.status).toBe("saving");
    wait(1);
    await landed();
    expect(result.current.status).toBe("serverDown");

    wait(2000);
    expect(sent(backend, "PUT")).toHaveLength(2);
    await landed();
    expect(result.current.status).toBe("saved");
    expect(backend.canvas.content("a1")).toBe("ab");
  });

  it("keeps a draft through React's trial mount and opens it as unsaved text", async () => {
    backend.canvas.add({ content: "a" });
    writeDraft({ artifact_id: "a1", base_version: 1, base: "a", text: "a!", saved_at: Date.now(), sent: [] });

    const { result } = await openCanvas({}, { strict: true });

    expect(result.current.state).toMatchObject({ phase: "ready", text: "a!", opened: "draft" });
    expect(result.current.status).toBe("unsaved");
    expect(readDraft("a1")?.text).toBe("a!");
    expect(sent(backend, "PUT")).toEqual([]);
  });

  it("opens text typed after a save that landed unheard as the person's draft, not as a clash", async () => {
    backend.canvas.add({ content: "a" });
    const left = await openCanvas();
    backend.canvas.loseNext("PUT");
    act(() => left.result.current.edit("ab"));
    wait(1500);
    await landed();
    expect(left.result.current.status).toBe("serverDown");
    act(() => left.result.current.edit("abc"));
    backend.canvas.refuseNext("PUT", 503);
    left.unmount();
    await landed();

    const { result } = await openCanvas();

    expect(result.current.state).toMatchObject({ text: "abc", opened: "draft", base: { version: 2 } });
    expect(result.current.status).toBe("unsaved");
  });
});

describe("flush", () => {
  it("waits for the save and gives the version that holds the text", async () => {
    backend.canvas.add({ content: "a" });
    const { result } = await openCanvas();
    act(() => result.current.edit("ab"));

    const version = await act(() => result.current.flush());

    expect(version).toBe(2);
    expect(sent(backend, "PUT").map((request) => request.body)).toEqual([{ content: "ab", base_version: 1 }]);
  });

  it("does not wait for keystrokes typed after it was called", async () => {
    backend.canvas.add({ content: "a" });
    const { result } = await openCanvas();
    const release = backend.canvas.holdNext("PUT", "reply");
    act(() => result.current.edit("ab"));
    let flushed: Promise<number | null> = Promise.resolve(null);
    act(() => {
      flushed = result.current.flush();
    });

    act(() => result.current.edit("abc"));
    await act(() => release());

    expect(await flushed).toBe(2);
    expect(sent(backend, "PUT")).toHaveLength(1);
    wait(1500);
    expect(sent(backend, "PUT").map((request) => request.body)).toEqual([
      { content: "ab", base_version: 1 },
      { content: "abc", base_version: 2 },
    ]);
  });

  it("gives null when the save meets a write to the same line", async () => {
    backend.canvas.add({ content: "a" });
    const { result } = await openCanvas();
    backend.canvas.onEvent = null;
    backend.canvas.write("a1", "x");
    act(() => result.current.edit("ab"));

    expect(await act(() => result.current.flush())).toBeNull();
    expect(result.current.status).toBe("conflict");
  });

  it("gives null for a canvas deleted meanwhile, and sends nothing", async () => {
    backend.canvas.add({ content: "a" });
    const { result } = await openCanvas();
    act(() => result.current.edit("ab"));
    act(() => backend.canvas.remove("a1"));

    expect(await act(() => result.current.flush())).toBeNull();
    expect(result.current.status).toBe("gone");
    expect(sent(backend, "PUT")).toEqual([]);
  });

  it("gives null when the first save fails, and says the server is down", async () => {
    backend.canvas.add({ content: "a" });
    const { result } = await openCanvas();
    backend.canvas.refuseNext("PUT", 503);
    act(() => result.current.edit("ab"));

    expect(await act(() => result.current.flush())).toBeNull();
    expect(result.current.status).toBe("serverDown");
  });
});
