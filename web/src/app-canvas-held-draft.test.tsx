import { fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { vi } from "./i18n/vi";
import { DRAFT_DELAY_MS, SAVE_DELAY_MS } from "./lib/canvas-runner";
import { conversation, openChat, openNote, startApp } from "./test/canvas-app";
import { landed, sent, stopServer, wait } from "./test/canvas-hook";
import { editor, saveState, typeInto } from "./test/canvas-panel";
import { askedToStay } from "./test/close-page";
import type { FakeBackend } from "./test/fake-backend";
import { refusingStorage } from "./test/memory-storage";

let backend: FakeBackend;

beforeEach(() => {
  backend = startApp();
});

afterEach(stopServer);

const TYPED = "chữ vừa gõ";
/** What the chat says of "Ghi chú" when its last save failed: its draft kept on this device, or by this tab alone. */
const notSaved = (kept: boolean) => screen.queryByText(vi.canvas.handoffFailed("Ghi chú", kept));
const notKept = () => screen.queryByText(vi.canvas.draftFailed);
const puts = () => sent(backend, "PUT").length;

async function settle() {
  await landed();
  await landed();
}

/** "Ghi chú" open beside conversation "Một" with `text` typed into it, and the draft written. */
async function typed(text = TYPED) {
  await openChat(1440);
  await openNote();
  typeInto(text);
  wait(DRAFT_DELAY_MS);
}

/** The person leaves for conversation "Hai" while the server fails the save, and comes back to the canvas. */
async function backAfterFailedSave() {
  backend.canvas.refuseNext("PUT", 500);
  fireEvent.click(conversation("Hai"));
  await settle();
  fireEvent.click(conversation("Một"));
  await settle();
  await openNote();
}

/** Cmd/Ctrl+S in the canvas. */
async function save() {
  fireEvent.keyDown(editor() as HTMLTextAreaElement, { key: "s", ctrlKey: true });
  await landed();
}

describe("a canvas opened again on a draft only this tab holds", () => {
  beforeEach(refusingStorage);

  it("is saved without another keystroke, and then nothing says it is not", async () => {
    await typed();
    await backAfterFailedSave();
    expect(editor()).toHaveValue(TYPED);
    expect(notSaved(false)).toBeInTheDocument();
    const before = puts();

    wait(DRAFT_DELAY_MS);
    expect(notKept()).toBeInTheDocument();
    wait(SAVE_DELAY_MS - DRAFT_DELAY_MS - 1);
    expect(puts()).toBe(before);
    wait(1);
    await settle();

    expect(sent(backend, "PUT").at(-1)?.body).toEqual({ content: TYPED, base_version: 1 });
    expect(backend.canvas.content("a1")).toBe(TYPED);
    expect(saveState()).toBe(vi.canvas.status.saved);
    expect(askedToStay()).toBe(false);
    expect(notSaved(false)).toBeNull();
    expect(notKept()).toBeNull();
  });

  it("is saved as it is left again at once, and the chat no longer says it is not", async () => {
    await typed();
    await backAfterFailedSave();
    expect(notSaved(false)).toBeInTheDocument();

    fireEvent.click(conversation("Hai"));
    await settle();

    expect(backend.canvas.content("a1")).toBe(TYPED);
    expect(notSaved(false)).toBeNull();
    expect(askedToStay()).toBe(false);
  });

  it("is asked about no more once saved by hand, though it merged with a newer version on the way in", async () => {
    backend.canvas.write("a1", "một\nhai\nba", { author: "user" });
    await typed("một!\nhai\nba");
    backend.canvas.refuseNext("PUT", 500);
    fireEvent.click(conversation("Hai"));
    await settle();
    // Someone else saves, unheard here.
    backend.canvas.onEvent = null;
    backend.canvas.write("a1", "một\nhai\nba!");
    fireEvent.click(conversation("Một"));
    await settle();
    await openNote();
    expect(editor()).toHaveValue("một!\nhai\nba!");
    expect(screen.getByText(vi.canvas.merged)).toBeInTheDocument();

    await save();

    expect(backend.canvas.content("a1")).toBe("một!\nhai\nba!");
    expect(askedToStay()).toBe(false);
    expect(notSaved(false)).toBeNull();
  });
});

describe("a canvas whose draft the browser refuses, while it stays open", () => {
  beforeEach(refusingStorage);

  it("says the draft is not kept only until the save lands", async () => {
    await typed();
    expect(notKept()).toBeInTheDocument();
    expect(askedToStay()).toBe(true);

    wait(SAVE_DELAY_MS - DRAFT_DELAY_MS);
    await settle();

    expect(saveState()).toBe(vi.canvas.status.saved);
    expect(notKept()).toBeNull();
    expect(askedToStay()).toBe(false);
  });

  it("says so again when the next words are refused as well", async () => {
    await typed();
    wait(SAVE_DELAY_MS - DRAFT_DELAY_MS);
    await settle();
    expect(notKept()).toBeNull();

    typeInto(`${TYPED} nữa`);
    wait(DRAFT_DELAY_MS);

    expect(notKept()).toBeInTheDocument();
  });
});

describe("a canvas opened again on a draft the browser stored", () => {
  it("shows the draft and sends nothing by itself", async () => {
    await typed();
    await backAfterFailedSave();
    expect(editor()).toHaveValue(TYPED);
    expect(notSaved(true)).toBeInTheDocument();
    const before = puts();

    wait(60_000);
    await settle();

    expect(puts()).toBe(before);
    expect(backend.canvas.content("a1")).toBe("");
    expect(notSaved(true)).toBeInTheDocument();
  });

  it("is said saved by the chat as well once the person saves it", async () => {
    await typed();
    await backAfterFailedSave();

    await save();

    expect(backend.canvas.content("a1")).toBe(TYPED);
    expect(notSaved(true)).toBeNull();
  });
});
