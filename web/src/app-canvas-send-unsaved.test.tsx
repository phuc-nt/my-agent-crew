import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { saveBody } from "./api/artifact-client";
import { DOCK_FLUSH_MS } from "./hooks/use-canvas-dock";
import { vi } from "./i18n/vi";
import { utf8Bytes } from "./lib/canvas-caps";
import { handoffsSettled } from "./lib/canvas-handoff";
import { saveDeadlineMs } from "./lib/canvas-requests";
import { SAVE_DELAY_MS } from "./lib/canvas-runner";
import { RETRY_DELAYS_MS } from "./lib/canvas-types";
import { bodies, box, openChat, openNote, posts, say, startApp, typeInCanvas } from "./test/canvas-app";
import { openBox, pressSend, typeQuestion } from "./test/canvas-ask";
import { landed, stopServer, wait } from "./test/canvas-hook";
import { editor, saveState } from "./test/canvas-panel";
import { pickIn } from "./test/canvas-pick";
import type { FakeBackend } from "./test/fake-backend";
import { slowUploads } from "./test/slow-link";

let backend: FakeBackend;

beforeEach(() => {
  backend = startApp();
});

afterEach(stopServer);

/** The line in the chat saying the last message went before its canvas was saved, or null. */
const unsavedNote = () => screen.queryByText(vi.canvas.sentUnsaved)?.closest<HTMLElement>(".notice") ?? null;

async function settle() {
  await landed();
  await landed();
  await landed();
}

describe("a message sent while the canvas's save is out on a link too slow for it", () => {
  // Near what a markdown canvas may hold: ten seconds of upload at the pace a save is first given.
  const PAGE = "x".repeat(500 * 1024);
  const BYTES = utf8Bytes(saveBody(PAGE, 1));
  // What the link takes to carry the page: longer than a save is given until three have gone unanswered.
  const UPLOAD_MS = 100_000;

  // A save still out when a test fails is left to the module once the app is gone, and would hold
  // up the next test's message: it is let run to its deadline first.
  afterEach(async () => {
    cleanup();
    await vitest.advanceTimersByTimeAsync(saveDeadlineMs(BYTES, 3));
    await handoffsSettled();
  });

  /** The first `count` saves each go unanswered to their deadline; the tab then waits to try again. */
  async function savesTimeOut(count: number) {
    wait(SAVE_DELAY_MS);
    await landed();
    for (let before = 0; before < count; before++) {
      if (before > 0) {
        wait(RETRY_DELAYS_MS[before - 1]);
        await landed();
      }
      wait(saveDeadlineMs(BYTES, before));
      await landed();
    }
    expect(saveState()).toBe(vi.canvas.status.slow);
  }

  it("goes once the save has had the time it was first given, with the version saved before, and says so", async () => {
    await openChat(1440);
    await openNote();
    slowUploads(UPLOAD_MS);
    typeInCanvas(PAGE);
    await savesTimeOut(3);
    // The save the message sets off is given long enough for this link; first it had forty seconds.
    expect(saveDeadlineMs(BYTES)).toBe(40_001);
    expect(saveDeadlineMs(BYTES, 3)).toBeGreaterThan(UPLOAD_MS);

    await say("đọc lại giúp tôi");
    expect(posts(backend)).toHaveLength(0);
    expect(box()).toHaveAttribute("readonly");
    expect(unsavedNote()).toBeNull();

    wait(DOCK_FLUSH_MS + saveDeadlineMs(BYTES) - 1);
    await settle();
    expect(posts(backend)).toHaveLength(0);
    wait(1);
    await settle();

    expect(bodies(backend)).toEqual([{ text: "đọc lại giúp tôi", canvas: { artifact_id: "a1", selection: null } }]);
    expect(box()).toHaveValue("");
    expect(box()).not.toHaveAttribute("readonly");
    expect(screen.queryByText(vi.canvas.savingFirst)).toBeNull();
    expect(unsavedNote()).toHaveAttribute("role", "status");
    expect(backend.canvas.content("a1")).toBe("");
  });

  it("leaves the save the longer time it was given: it lands after the message went, and the line stays true of that message", async () => {
    await openChat(1440);
    await openNote();
    slowUploads(UPLOAD_MS);
    typeInCanvas(PAGE);
    await savesTimeOut(3);
    await say("đọc lại giúp tôi");
    wait(DOCK_FLUSH_MS + saveDeadlineMs(BYTES));
    await settle();
    expect(posts(backend)).toHaveLength(1);

    wait(UPLOAD_MS - DOCK_FLUSH_MS - saveDeadlineMs(BYTES));
    await settle();

    expect(backend.canvas.content("a1") === PAGE).toBe(true);
    expect(saveState()).toBe(vi.canvas.status.saved);
    expect(unsavedNote()).not.toBeNull();
  });
});

describe("the line saying a message went before its canvas was saved", () => {
  /** "Ghi chú" open with typing the server failed to save, and a message sent over it. */
  async function sentOverFailedSave() {
    await openChat(1440);
    await openNote();
    typeInCanvas("đang gõ");
    backend.canvas.refuseNext("PUT", 500);
    await say("tin một");
    expect(posts(backend)).toHaveLength(1);
    expect(backend.canvas.content("a1")).toBe("");
  }

  it("is shown in the chat, in words, when the save failed and the message went all the same", async () => {
    await sentOverFailedSave();

    expect(unsavedNote()).toHaveClass("notice", "warn", "canvas-notice");
    expect(unsavedNote()).toHaveTextContent("Canvas chưa lưu xong nên tin vừa gửi đi kèm bản đã lưu gần nhất");
    expect(document.querySelector(".main")).toContainElement(unsavedNote());
  });

  it("goes with the next message, sent once the canvas is saved", async () => {
    await sentOverFailedSave();

    typeInCanvas("đang gõ thêm");
    await say("tin hai");

    expect(posts(backend)).toHaveLength(2);
    expect(backend.canvas.content("a1")).toBe("đang gõ thêm");
    expect(unsavedNote()).toBeNull();
  });

  /** The person asks about the words they typed in the canvas, and the question is let run. */
  async function askAboutTyping() {
    pickIn(editor() as HTMLTextAreaElement, "đang gõ");
    openBox();
    typeQuestion("đoạn này ổn chưa?");
    pressSend();
    await settle();
    await landed();
  }

  it("goes with a question about a passage of the canvas, which went with the canvas saved", async () => {
    await sentOverFailedSave();
    expect(unsavedNote()).not.toBeNull();

    await askAboutTyping();

    expect(bodies(backend)[1]).toEqual({
      text: "đoạn này ổn chưa?",
      canvas: { artifact_id: "a1", selection: { version: 2, text: "đang gõ", line_start: 1, line_end: 1 } },
    });
    expect(backend.canvas.content("a1")).toBe("đang gõ");
    expect(unsavedNote()).toBeNull();
  });

  it("stays when that question did not reach the server: the last message that went is still the one it tells of", async () => {
    await sentOverFailedSave();
    const real = backend.fetch;
    vitest.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) =>
      String(input).endsWith("/messages") ? Promise.reject(new TypeError("Failed to fetch")) : real(input, init),
    );

    await askAboutTyping();

    expect(posts(backend)).toHaveLength(1);
    expect(backend.canvas.content("a1")).toBe("đang gõ");
    expect(unsavedNote()).not.toBeNull();
  });

  it("is put away by its own button, and by nothing else on the way", async () => {
    await sentOverFailedSave();
    const note = unsavedNote() as HTMLElement;

    fireEvent.click(within(note).getByRole("button", { name: vi.canvas.dismiss }));

    expect(unsavedNote()).toBeNull();
    expect(posts(backend)).toHaveLength(1);
  });

  it("is not shown for a message the server did not take: nothing went with any version", async () => {
    await openChat(1440);
    await openNote();
    typeInCanvas("đang gõ");
    backend.canvas.refuseNext("PUT", 422);
    const real = backend.fetch;
    vitest.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) =>
      String(input).endsWith("/messages") ? Promise.reject(new TypeError("Failed to fetch")) : real(input, init),
    );

    await say("tin một");

    expect(box()).toHaveValue("tin một");
    expect(screen.getByTestId("notice")).toBeInTheDocument();
    expect(unsavedNote()).toBeNull();
  });

  it("is not shown when the canvas was saved before the message went, nor where no canvas is open", async () => {
    await openChat(1440);
    await say("chào");
    expect(unsavedNote()).toBeNull();

    await openNote();
    typeInCanvas("bản sửa");
    await say("đọc lại giúp tôi");

    expect(posts(backend)).toHaveLength(2);
    expect(backend.canvas.content("a1")).toBe("bản sửa");
    expect(unsavedNote()).toBeNull();
  });
});
