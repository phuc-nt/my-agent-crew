import { fireEvent, render, screen } from "@testing-library/react";
import { vi as vitest } from "vitest";
import { App } from "../app";
import { vi } from "../i18n/vi";
import { landed, startServer } from "./canvas-hook";
import { type FakeBackend, FakeEventSource } from "./fake-backend";
import { forgetScreenListeners, screenAt } from "./screen-width";

/**
 * The whole app on the fake server of `startServer`, for tests that open a canvas beside a chat:
 * two conversations, "Một" and "Hai", and one canvas, "Ghi chú" (a1), shared with "Một".
 */
export function startApp(): FakeBackend {
  const backend = startServer();
  FakeEventSource.instances = [];
  vitest.stubGlobal("EventSource", FakeEventSource);
  forgetScreenListeners();
  window.location.hash = "";
  backend.create({ title: "Một" });
  backend.create({ title: "Hai" });
  backend.canvas.add({ title: "Ghi chú", conversationIds: ["c1"] });
  return backend;
}

export const conversation = (title: string) => screen.getByRole("button", { name: new RegExp(title), hidden: true });
export const canvasButton = () => screen.getByRole("button", { name: vi.canvas.buttonLabel(1) });
export const layout = () => document.querySelector(".layout") as HTMLElement;
export const box = () => screen.getByRole("textbox", { name: vi.composerPlaceholder });

/** The app at `px` wide on conversation "Một". */
export async function openChat(px: number) {
  screenAt(px);
  render(<App />);
  await landed();
  await landed();
  fireEvent.click(conversation("Một"));
  await landed();
  await landed();
}

/** Opens the dock's list with the Canvas button, then "Ghi chú" from it. */
export async function openNote() {
  fireEvent.click(canvasButton());
  await landed();
  fireEvent.click(screen.getByRole("button", { name: /Ghi chú/ }));
  await landed();
}

/** The person types into the canvas's text. */
export function typeInCanvas(text: string) {
  fireEvent.change(screen.getByRole("textbox", { name: vi.canvas.editor }), { target: { value: text } });
}

/** The person writes `text` in the box and presses Enter, and the send is let run. */
export async function say(text: string) {
  fireEvent.change(box(), { target: { value: text } });
  fireEvent.keyDown(box(), { key: "Enter" });
  await landed();
  await landed();
  await landed();
}

/** What reached the server, as "METHOD /path" in the order it came. */
export const traffic = (backend: FakeBackend) => backend.requests.map((r) => `${r.method} ${r.path}`);

/** The messages posted to a conversation, oldest first. */
export const posts = (backend: FakeBackend, id = "c1") =>
  backend.requests.filter((r) => r.method === "POST" && r.path === `/conversations/${id}/messages`);

/** What each of those messages said. Every send goes under a name of its own, which is
 *  checked here and left out, so a test reads only the text and the canvas it is about. */
export const bodies = (backend: FakeBackend, id = "c1") =>
  posts(backend, id).map((r) => {
    const { request_id: name, ...said } = r.body as { request_id?: unknown };
    if (typeof name !== "string" || !/^[0-9a-f]{32}$/.test(name)) {
      throw new Error(`a message went with no name of its own: ${JSON.stringify(r.body)}`);
    }
    return said;
  });

/** The writes to the conversation's open canvas. */
export const focusWrites = (backend: FakeBackend, id = "c1") =>
  backend.requests.filter((r) => r.method === "PUT" && r.path === `/conversations/${id}/canvas`);
