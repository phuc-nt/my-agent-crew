import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { artifactApi } from "../api/artifact-client";
import { landed, sent, startServer, stopServer, wait } from "../test/canvas-hook";
import { askedToStay } from "../test/close-page";
import type { FakeBackend } from "../test/fake-backend";
import { memoryStorage, refusingStorage } from "../test/memory-storage";
import { type CanvasDraft, heldInTab, readDraft, writeDraft } from "./canvas-draft";
import { CanvasRunner, DRAFT_DELAY_MS, SAVE_DELAY_MS } from "./canvas-runner";

let backend: FakeBackend;
/** What the panel was last told of the draft: whether this device failed to keep it. */
let told: boolean[];

beforeEach(() => {
  backend = startServer();
  refusingStorage();
  told = [];
});

afterEach(stopServer);

const LINES = "one\ntwo\nthree";
const puts = () => sent(backend, "PUT").map((request) => request.body);
const save = (runner: CanvasRunner) => runner.send({ type: "saveDue", reason: "manual" });

/** A draft of a1 edited from "a" at v1, unless `over` says otherwise, as an earlier panel left it. */
function left(over: Partial<CanvasDraft> = {}): boolean {
  return writeDraft({ artifact_id: "a1", base_version: 1, base: "a", text: "ab", saved_at: 0, sent: [], ...over });
}

/** A runner on canvas a1 that has not read yet. */
function runnerOn(): CanvasRunner {
  const runner: CanvasRunner = new CanvasRunner("a1", () => told.push(runner.draftFailed));
  return runner;
}

/** Canvas a1 holding `content` at v1, opened once its first read landed. */
async function opened(content = "a"): Promise<CanvasRunner> {
  backend.canvas.add({ content });
  const runner = runnerOn();
  runner.start();
  await landed();
  expect(runner.state.phase).toBe("ready");
  return runner;
}

describe("a canvas opened on a draft only this tab holds", () => {
  it("saves the draft by itself, as long after it opened as after a keystroke", async () => {
    expect(left()).toBe(false);
    const runner = await opened();
    expect(runner.state.text).toBe("ab");

    wait(SAVE_DELAY_MS - 1);
    expect(puts()).toEqual([]);
    wait(1);
    expect(puts()).toEqual([{ content: "ab", base_version: 1 }]);

    await landed();
    expect(backend.canvas.content("a1")).toBe("ab");
    expect(readDraft("a1")).toBeNull();
    expect(askedToStay()).toBe(false);
  });

  it("says this device kept no draft once the draft is written again, and no longer once the save lands", async () => {
    left();
    const runner = await opened();

    wait(DRAFT_DELAY_MS);
    expect(runner.draftFailed).toBe(true);
    expect(told.at(-1)).toBe(true);

    wait(SAVE_DELAY_MS - DRAFT_DELAY_MS);
    await landed();

    expect(runner.draftFailed).toBe(false);
    expect(told.at(-1)).toBe(false);
  });

  it("saves what the draft merged into, on the version it merged with", async () => {
    backend.canvas.add({ content: LINES });
    left({ base: LINES, text: "one!\ntwo\nthree" });
    backend.canvas.write("a1", "one\ntwo\nthree!");
    const runner = runnerOn();
    runner.start();
    await landed();
    expect(runner.state.opened).toBe("merged");

    wait(SAVE_DELAY_MS);
    expect(puts()).toEqual([{ content: "one!\ntwo\nthree!", base_version: 2 }]);
  });

  it("holds nothing after a merged draft was saved by hand before it was written again", async () => {
    backend.canvas.add({ content: LINES });
    left({ base: LINES, text: "one!\ntwo\nthree" });
    backend.canvas.write("a1", "one\ntwo\nthree!");
    const runner = runnerOn();
    runner.start();
    await landed();

    save(runner);
    await landed();

    expect(backend.canvas.content("a1")).toBe("one!\ntwo\nthree!");
    expect(askedToStay()).toBe(false);
    expect(heldInTab("a1")).toBe(false);
  });

  it("sends nothing while the draft and the newest version cannot both stand, and says the draft is not kept", async () => {
    backend.canvas.add({ content: "a" });
    left({ text: "mine" });
    backend.canvas.write("a1", "theirs");
    const runner = runnerOn();
    runner.start();
    await landed();
    expect(runner.state.conflict).not.toBeNull();

    wait(DRAFT_DELAY_MS);
    expect(runner.draftFailed).toBe(true);
    wait(60_000);
    await landed();

    expect(puts()).toEqual([]);
    expect(readDraft("a1")?.text).toBe("mine");
    expect(askedToStay()).toBe(true);
  });

  it("is saved by itself when the first read failed and the next one brought it", async () => {
    backend.canvas.add({ content: "a" });
    left();
    backend.canvas.refuseNext("GET", 500);
    const runner = runnerOn();
    runner.start();
    await landed();
    expect(runner.state.phase).toBe("failed");
    wait(60_000);
    expect(puts()).toEqual([]);

    runner.send({ type: "resync" });
    await landed();
    expect(runner.state.text).toBe("ab");
    wait(SAVE_DELAY_MS - 1);
    expect(puts()).toEqual([]);
    wait(1);

    expect(puts()).toEqual([{ content: "ab", base_version: 1 }]);
  });

  it("sets no save going when the runner is let go as its first read arrives", async () => {
    backend.canvas.add({ content: "a" });
    left();
    const read = artifactApi.get;
    let arrive = () => {};
    const onTheWay = new Promise<void>((resolve) => {
      arrive = resolve;
    });
    vitest.spyOn(artifactApi, "get").mockImplementation(async (id) => {
      const detail = await read(id);
      await onTheWay;
      return detail;
    });
    const runner = runnerOn();
    runner.start();
    await landed();

    runner.detach();
    arrive();
    await landed();
    expect(runner.state.phase).toBe("ready");

    wait(60_000);
    await landed();
    expect(puts()).toEqual([]);
  });
});

describe("a canvas opened on a draft the browser stored", () => {
  it("shows the draft and sends nothing until the person saves or types", async () => {
    memoryStorage();
    expect(left()).toBe(true);
    const runner = await opened();
    expect(runner.state.text).toBe("ab");
    expect(runner.state.opened).toBe("draft");

    wait(60_000);
    await landed();
    expect(puts()).toEqual([]);
    expect(runner.draftFailed).toBe(false);

    save(runner);
    expect(puts()).toEqual([{ content: "ab", base_version: 1 }]);
  });
});
