import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { bodies, box, conversation, focusWrites, layout, openChat, openNote, say, startApp } from "./test/canvas-app";
import { NOTE } from "./test/canvas-dock-hook";
import { landed, stopServer } from "./test/canvas-hook";
import type { FakeBackend } from "./test/fake-backend";
import { screenAt } from "./test/screen-width";

let backend: FakeBackend;

beforeEach(() => {
  backend = startApp();
});

afterEach(stopServer);

const settle = async () => {
  await landed();
  await landed();
};

describe("closing the canvas, as far as the next message goes", () => {
  it("tells the server once on a wide screen, and the next message names no canvas", async () => {
    await openChat(1440);
    await openNote();
    expect(focusWrites(backend)).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.close }));
    await settle();
    expect(focusWrites(backend).map((request) => request.body)).toEqual([{ artifact_id: null }]);
    await say("sau khi đóng");

    expect(bodies(backend)).toEqual([{ text: "sau khi đóng", canvas: { artifact_id: null } }]);
    expect(focusWrites(backend)).toHaveLength(1);
  });

  it("tells nothing on a narrow screen, where the canvas put away is still the one the message names", async () => {
    await openChat(1000);
    await openNote();

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.close }));
    await settle();
    expect(focusWrites(backend)).toEqual([]);
    await say("sau khi đóng");

    expect(bodies(backend)).toEqual([{ text: "sau khi đóng", canvas: { artifact_id: "a1", selection: null } }]);
  });
});

describe("the canvas the server has open in a conversation", () => {
  beforeEach(() => {
    backend.canvas.add({ id: NOTE, title: "Cũ", conversationIds: ["c1"] });
    backend.canvas.focus.open("c1", NOTE);
  });

  it("opens beside the chat without taking the focus from the box, and writes nothing", async () => {
    const release = backend.canvas.holdNext("GET /conversations/c1/canvas", "reply");
    screenAt(1440);
    render(<App />);
    await settle();
    fireEvent.click(conversation("Một"));
    await settle();
    box().focus();
    expect(layout()).not.toHaveClass("with-canvas");

    await act(() => release());
    await settle();

    expect(layout()).toHaveClass("with-canvas");
    expect(box()).toHaveFocus();
    // The next words go where the focus is: into the box, not into the canvas or its name.
    fireEvent.change(document.activeElement as HTMLElement, { target: { value: "xin chào" } });
    await settle();
    expect(box()).toHaveValue("xin chào");
    expect(backend.requests.filter((request) => ["PUT", "PATCH"].includes(request.method))).toEqual([]);
  });

  it("carries no canvas from a read that was answered after the person went to another conversation", async () => {
    const release = backend.canvas.holdNext("GET /conversations/c1/canvas", "reply");
    await openChat(1440);
    fireEvent.click(conversation("Hai"));
    await settle();
    await act(() => release());
    await settle();

    await say("tin ở Hai");

    expect(layout()).not.toHaveClass("with-canvas");
    expect(bodies(backend, "c2")).toEqual([{ text: "tin ở Hai" }]);
  });
});
