import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { landed, startServer, stopServer } from "../test/canvas-hook";
import { leftCanvas } from "../test/canvas-left";
import type { FakeBackend } from "../test/fake-backend";
import { readDraft, writeDraft } from "./canvas-draft";
import { canvasSaved, onCanvasSaved, saveInBackground } from "./canvas-handoff";
import { openState } from "./canvas-machine";
import { CanvasRunner } from "./canvas-runner";

let backend: FakeBackend;
let heard: string[];
let unsubscribe: () => void;

beforeEach(() => {
  backend = startServer();
  heard = [];
  unsubscribe = onCanvasSaved((id) => heard.push(id));
});

afterEach(() => {
  unsubscribe();
  stopServer();
});

const save = (runner: CanvasRunner) => runner.send({ type: "saveDue", reason: "manual" });

/** A runner on canvas a1, "a" at v1, once its first read landed. */
async function opened(): Promise<CanvasRunner> {
  backend.canvas.add({ content: "a" });
  const runner = new CanvasRunner("a1", () => {});
  runner.start();
  await landed();
  expect(runner.state.phase).toBe("ready");
  return runner;
}

describe("word that a canvas has nothing left unsaved", () => {
  it("comes when a save left behind lands", async () => {
    await saveInBackground(leftCanvas("a1", async () => 3));

    expect(heard).toEqual(["a1"]);
  });

  it("does not come when a save left behind fails", async () => {
    await saveInBackground(leftCanvas("a1", async () => null));

    expect(heard).toEqual([]);
  });

  it("does not come when the save that lands is outlived by a draft of words typed since", async () => {
    // The canvas was opened again and left again: that later save failed, and its draft is kept.
    writeDraft({ artifact_id: "a1", base_version: 1, base: "a", text: "typed later", saved_at: 0, sent: [] });
    const earlier = { ...openState("a1", null), text: "typed first" };

    await saveInBackground(leftCanvas("a1", async () => 2, { state: earlier }));

    expect(readDraft("a1")?.text).toBe("typed later");
    expect(heard).toEqual([]);
  });

  it("comes when the save that lands held the very words of the draft, which goes with it", async () => {
    writeDraft({ artifact_id: "a1", base_version: 1, base: "a", text: "typed first", saved_at: 0, sent: [] });
    const left = { ...openState("a1", null), text: "typed first" };

    await saveInBackground(leftCanvas("a1", async () => 2, { state: left }));

    expect(readDraft("a1")).toBeNull();
    expect(heard).toEqual(["a1"]);
  });

  it("comes once for a runner let go with text to save: from its handoff, not from the runner as well", async () => {
    const runner = await opened();
    runner.edit("ab");
    runner.detach();

    await saveInBackground(runner);

    expect(backend.canvas.content("a1")).toBe("ab");
    expect(heard).toEqual(["a1"]);
  });

  it("comes from an open canvas when its save lands with nothing typed since", async () => {
    const runner = await opened();
    runner.edit("ab");
    expect(heard).toEqual([]);

    save(runner);
    expect(heard).toEqual([]);
    await landed();

    expect(heard).toEqual(["a1"]);
  });

  it("does not come from an open canvas while text typed since the save went out is unsaved", async () => {
    const runner = await opened();
    runner.edit("ab");
    const release = backend.canvas.holdNext("PUT", "reply");
    save(runner);
    runner.edit("abc");

    await release();
    await landed();
    expect(backend.canvas.content("a1")).toBe("ab");
    expect(heard).toEqual([]);

    save(runner);
    await landed();
    expect(heard).toEqual(["a1"]);
  });

  it("does not come while a save cannot go: the text and the newest version cannot both stand", async () => {
    const runner = await opened();
    runner.edit("mine");
    backend.canvas.write("a1", "theirs");

    save(runner);
    await landed();

    expect(runner.state.conflict).not.toBeNull();
    expect(heard).toEqual([]);
  });

  it("is heard by every listener still subscribed, each time by its own subscription", () => {
    const other: string[] = [];
    const listener = (id: string) => other.push(id);
    const first = onCanvasSaved(listener);
    const second = onCanvasSaved(listener);

    canvasSaved("a1");
    expect(other).toEqual(["a1", "a1"]);

    first();
    canvasSaved("a2");
    expect(other).toEqual(["a1", "a1", "a2"]);

    second();
    canvasSaved("a3");
    expect(other).toEqual(["a1", "a1", "a2"]);
    expect(heard).toEqual(["a1", "a2", "a3"]);
  });
});
