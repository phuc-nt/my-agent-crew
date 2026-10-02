import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { readDraft } from "../lib/canvas-draft";
import { DRAFT_DELAY_MS } from "../lib/canvas-runner";
import { landed, openCanvas, sent, setVisibility, startServer, stopServer, wait } from "../test/canvas-hook";
import type { FakeBackend } from "../test/fake-backend";
import { memoryStorage, refusingStorage } from "../test/memory-storage";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
});

afterEach(stopServer);

const BIG = "x".repeat(100 * 1024);

describe("saving a canvas as the person types", () => {
  it("saves once, 1.5 s after the last of thirty keystrokes and not a moment sooner", async () => {
    backend.canvas.add({ content: "a" });
    const { result } = await openCanvas();

    for (let typed = 1; typed <= 30; typed++) {
      act(() => result.current.edit(`a${"b".repeat(typed)}`));
      wait(100);
    }
    wait(1399);
    expect(sent(backend, "PUT")).toEqual([]);
    wait(1);

    expect(sent(backend, "PUT").map((request) => request.body)).toEqual([
      { content: `a${"b".repeat(30)}`, base_version: 1 },
    ]);
  });

  it("does not put the save off for an edit that changes nothing", async () => {
    backend.canvas.add({ content: "a" });
    const { result } = await openCanvas();
    act(() => result.current.edit("ab"));
    wait(1000);

    act(() => result.current.edit("ab"));
    wait(500);

    expect(sent(backend, "PUT")).toHaveLength(1);
  });

  it("saves at once on Cmd/Ctrl+S, and not again when the pause in typing ends", async () => {
    backend.canvas.add({ content: "a" });
    const { result } = await openCanvas();
    act(() => result.current.edit("ab"));

    act(() => result.current.save());
    expect(sent(backend, "PUT")).toHaveLength(1);
    await landed();
    wait(1500);

    expect(sent(backend, "PUT")).toHaveLength(1);
    expect(result.current.status).toBe("saved");
  });

  it("says so when this device cannot keep the draft, until it can again", async () => {
    backend.canvas.add({ content: "a" });
    refusingStorage();
    const { result } = await openCanvas();
    act(() => result.current.edit("ab"));

    wait(299);
    expect(result.current.draftFailed).toBe(false);
    wait(1);
    expect(result.current.draftFailed).toBe(true);

    memoryStorage();
    act(() => result.current.edit("abc"));
    wait(DRAFT_DELAY_MS);
    expect(result.current.draftFailed).toBe(false);
  });
});

describe("a canvas the page may be leaving", () => {
  it("saves 100 KB as a plain request when the tab hides, the draft holding the keystroke just before", async () => {
    backend.canvas.add({ content: BIG });
    const { result } = await openCanvas();
    act(() => result.current.edit(`${BIG}!`));
    wait(50);

    setVisibility("hidden");

    expect(sent(backend, "PUT")).toEqual([
      { method: "PUT", path: "/artifacts/a1", body: { content: `${BIG}!`, base_version: 1 } },
    ]);
    expect(readDraft("a1")?.text).toBe(`${BIG}!`);
  });

  it("saves 100 KB as a plain request when the panel goes, keeping the whole draft until it lands", async () => {
    backend.canvas.add({ content: BIG });
    const { result, unmount } = await openCanvas();
    act(() => result.current.edit(`${BIG}!`));

    unmount();

    expect(sent(backend, "PUT").map((request) => request.keepalive)).toEqual([undefined]);
    expect(readDraft("a1")?.text).toBe(`${BIG}!`);
    await landed();
    expect(backend.canvas.content("a1")).toBe(`${BIG}!`);
    expect(readDraft("a1")).toBeNull();
  });

  it("keeps a small canvas's last save alive past the page, on the version it was edited from", async () => {
    const text = "y".repeat(10 * 1024);
    backend.canvas.add({ content: text, version: 3 });
    const { result, unmount } = await openCanvas();
    act(() => result.current.edit(`${text}!`));

    unmount();

    expect(sent(backend, "PUT")).toEqual([
      { method: "PUT", path: "/artifacts/a1", body: { content: `${text}!`, base_version: 3 }, keepalive: true },
    ]);
    await landed();
    expect(backend.canvas.content("a1")).toBe(`${text}!`);
  });

  it("writes the draft at once when the panel goes 100 ms after the last keystroke", async () => {
    backend.canvas.add({ content: "a" });
    const { result, unmount } = await openCanvas();
    act(() => result.current.edit("ab"));
    wait(100);

    unmount();

    expect(readDraft("a1")).toMatchObject({ text: "ab", base: "a", base_version: 1 });
    await landed();
  });

  it("writes the draft at once when the page is being hidden for good", async () => {
    backend.canvas.add({ content: "a" });
    const { result } = await openCanvas();
    act(() => result.current.edit("ab"));
    wait(100);

    act(() => {
      window.dispatchEvent(new Event("pagehide"));
    });

    expect(readDraft("a1")).toMatchObject({ text: "ab", base: "a", base_version: 1 });
  });

  it("forgets the draft of a canvas deleted while open once its panel goes", async () => {
    backend.canvas.add({ content: "a" });
    const { result, unmount } = await openCanvas();
    act(() => result.current.edit("ab"));
    wait(DRAFT_DELAY_MS);
    expect(readDraft("a1")?.text).toBe("ab");

    act(() => backend.canvas.remove("a1"));
    expect(result.current.state.text).toBe("ab");
    unmount();

    expect(readDraft("a1")).toBeNull();
    expect(sent(backend, "PUT")).toEqual([]);
  });
});
