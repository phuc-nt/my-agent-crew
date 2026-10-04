import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { landed, startServer, stopServer, wait } from "../test/canvas-hook";
import { askedToStay } from "../test/close-page";
import type { FakeBackend } from "../test/fake-backend";
import { refusingStorage } from "../test/memory-storage";
import { readDraft } from "./canvas-draft";
import { CanvasRunner, DRAFT_DELAY_MS, SAVE_DELAY_MS } from "./canvas-runner";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
  refusingStorage();
});

afterEach(stopServer);

const LINES = "one\ntwo\nthree";
const save = (runner: CanvasRunner) => runner.send({ type: "saveDue", reason: "manual" });

/** Canvas a1 holding `content` at v1, opened once its first read landed. */
async function opened(content = "a"): Promise<CanvasRunner> {
  backend.canvas.add({ content });
  const runner = new CanvasRunner("a1", () => {});
  runner.start();
  await landed();
  expect(runner.state.phase).toBe("ready");
  return runner;
}

describe("the draft this tab holds of a canvas that is open", () => {
  it("goes once a save merged with someone else's version lands, though it holds the text from before the merge", async () => {
    const runner = await opened(LINES);
    runner.edit("one!\ntwo\nthree");
    wait(DRAFT_DELAY_MS);
    expect(readDraft("a1")?.text).toBe("one!\ntwo\nthree");
    backend.canvas.write("a1", "one\ntwo\nthree!");

    wait(SAVE_DELAY_MS - DRAFT_DELAY_MS);
    await landed();
    await landed();

    expect(backend.canvas.content("a1")).toBe("one!\ntwo\nthree!");
    expect(readDraft("a1")).toBeNull();
    expect(askedToStay()).toBe(false);
    expect(runner.draftFailed).toBe(false);
  });

  it("stays while text typed since the save went out is still unsaved", async () => {
    const runner = await opened();
    runner.edit("ab");
    const release = backend.canvas.holdNext("PUT", "reply");
    save(runner);
    runner.edit("abc");
    wait(DRAFT_DELAY_MS);
    expect(runner.draftFailed).toBe(true);

    await release();
    await landed();

    expect(backend.canvas.content("a1")).toBe("ab");
    expect(readDraft("a1")?.text).toBe("abc");
    expect(askedToStay()).toBe(true);
    expect(runner.draftFailed).toBe(true);
  });

  it("goes once a read shows that a save whose reply was lost did land", async () => {
    const runner = await opened();
    const arrive = backend.canvas.holdNext("GET", "request");
    runner.send({ type: "resync" });
    runner.edit("ab");
    wait(DRAFT_DELAY_MS);
    backend.canvas.loseNext("PUT");
    save(runner);
    await landed();
    expect(backend.canvas.content("a1")).toBe("ab");
    expect(askedToStay()).toBe(true);

    await arrive();
    await landed();

    expect(runner.state.base.version).toBe(2);
    expect(readDraft("a1")).toBeNull();
    expect(askedToStay()).toBe(false);
    expect(runner.draftFailed).toBe(false);
  });
});
