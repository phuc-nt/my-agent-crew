import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { vi } from "./i18n/vi";
import { conversation, openChat, openNote, startApp } from "./test/canvas-app";
import { DRAFT_DELAY_MS } from "./lib/canvas-runner";
import { landed, sent, stopServer, wait } from "./test/canvas-hook";
import { editor, typeInto } from "./test/canvas-panel";
import { askedToStay } from "./test/close-page";
import type { FakeBackend } from "./test/fake-backend";
import { refusingStorage } from "./test/memory-storage";

let backend: FakeBackend;

beforeEach(() => {
  backend = startApp();
  refusingStorage();
});

afterEach(stopServer);

const TYPED = "chữ vừa gõ";
const notSaved = () => screen.queryByText(vi.canvas.handoffFailed("Ghi chú", false));
const press = (name: string) => fireEvent.click(screen.getByRole("button", { name }));

async function settle() {
  await landed();
  await landed();
}

/** "Ghi chú" open beside conversation "Một" with `TYPED` in it, unsaved. */
async function typed() {
  await openChat(1440);
  await openNote();
  typeInto(TYPED);
}

/** The person stops typing and closes the panel, whose save the server fails. */
async function closeOverFailedSave() {
  wait(DRAFT_DELAY_MS);
  backend.canvas.refuseNext("PUT", 500);
  press(vi.canvas.close);
  await settle();
}

/** The person leaves for conversation "Hai" and comes back to the canvas. */
async function awayAndBack() {
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

describe("text typed into a canvas where the browser refuses to keep drafts", () => {
  it("is back as an unsaved draft after a close whose saves the server failed, and the next save sends it", async () => {
    await typed();
    await closeOverFailedSave();
    backend.canvas.refuseNext("PUT", 500);

    press(vi.canvas.closeAnywayTabOnly);
    await settle();

    expect(editor()).toBeNull();
    expect(notSaved()).toBeInTheDocument();
    expect(backend.canvas.content("a1")).toBe("");
    expect(askedToStay()).toBe(true);

    await openNote();
    expect(editor()).toHaveValue(TYPED);
    expect(screen.getByText(vi.canvas.draftOpened)).toBeInTheDocument();
    expect(askedToStay()).toBe(true);

    await save();
    expect(sent(backend, "PUT").at(-1)?.body).toEqual({ content: TYPED, base_version: 1 });
    expect(backend.canvas.content("a1")).toBe(TYPED);
    expect(askedToStay()).toBe(false);
  });

  it("is back against the newer version after a close whose save met someone else's", async () => {
    await typed();
    await closeOverFailedSave();
    // Someone else saves, unheard here, and the save handed off as the panel goes meets it.
    backend.canvas.onEvent = null;
    backend.canvas.write("a1", "chữ của người khác");

    press(vi.canvas.closeAnywayTabOnly);
    await settle();

    expect(sent(backend, "PUT")).toHaveLength(2);
    expect(notSaved()).toBeInTheDocument();
    expect(askedToStay()).toBe(true);

    await openNote();
    expect(editor()).toHaveValue(TYPED);
    press(vi.canvas.keepMine);
    await landed();

    expect(backend.canvas.content("a1")).toBe(TYPED);
    expect(askedToStay()).toBe(false);
  });

  it("is back after the conversation changed under a save the server failed", async () => {
    await typed();
    backend.canvas.refuseNext("PUT", 500);

    await awayAndBack();

    expect(notSaved()).toBeInTheDocument();
    expect(editor()).toHaveValue(TYPED);
    expect(screen.getByText(vi.canvas.draftOpened)).toBeInTheDocument();
    expect(askedToStay()).toBe(true);

    await save();
    expect(backend.canvas.content("a1")).toBe(TYPED);
    expect(askedToStay()).toBe(false);
  });

  it("is asked about no more once its canvas is deleted, the panel long gone", async () => {
    await typed();
    backend.canvas.refuseNext("PUT", 500);
    fireEvent.click(conversation("Hai"));
    await settle();
    expect(askedToStay()).toBe(true);

    act(() => backend.canvas.remove("a1"));

    expect(askedToStay()).toBe(false);
  });

  it("is still asked about when someone else only saves its canvas anew, and is there on the way back", async () => {
    await typed();
    backend.canvas.refuseNext("PUT", 500);
    fireEvent.click(conversation("Hai"));
    await settle();

    act(() => void backend.canvas.write("a1", "chữ của người khác"));

    expect(askedToStay()).toBe(true);
    fireEvent.click(conversation("Một"));
    await settle();
    await openNote();
    expect(editor()).toHaveValue(TYPED);
  });

  it("is not asked about when the save handed off lands", async () => {
    await typed();

    fireEvent.click(conversation("Hai"));
    await settle();

    expect(notSaved()).toBeNull();
    expect(backend.canvas.content("a1")).toBe(TYPED);
    expect(askedToStay()).toBe(false);
  });
});
