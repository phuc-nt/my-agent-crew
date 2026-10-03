import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { canvasButton, conversation, layout, openChat, openNote, startApp } from "./test/canvas-app";
import { landed, sent, stopServer } from "./test/canvas-hook";
import { editor, typeInto } from "./test/canvas-panel";
import { type FakeBackend, fakeRun } from "./test/fake-backend";
import { resize, screenAt } from "./test/screen-width";

let backend: FakeBackend;
const DAY = 24 * 60 * 60 * 1000;

beforeEach(() => {
  backend = startApp();
});

afterEach(stopServer);

const main = () => document.querySelector("main") as HTMLElement;
const typedAt = (text: string) => ({ content: text, base_version: 1 });

describe("the canvas dock beside a wide conversation", () => {
  it("opens as a tab over the activity, in a column its edge widens, and keeps both mounted", async () => {
    await openChat(1440);
    const activity = screen.getByTestId("conversation-activity");
    expect(layout()).toHaveClass("with-activity");

    fireEvent.click(canvasButton());
    await landed();
    expect(screen.getByRole("button", { name: vi.canvas.newCanvas })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: /Ghi chú/ }));
    await landed();

    expect(layout()).toHaveClass("with-canvas");
    const tabs = within(screen.getByRole("tablist")).getAllByRole("tab");
    expect(tabs.map((tab) => [tab.textContent, tab.getAttribute("aria-selected")])).toEqual([
      [vi.canvas.tabs.activity, "false"],
      [vi.canvas.tabs.canvas, "true"],
    ]);
    const edge = screen.getByRole("separator", { name: vi.canvas.resize });
    expect(edge).toHaveAttribute("aria-valuenow", "584");
    fireEvent.keyDown(edge, { key: "ArrowLeft" });
    expect(edge).toHaveAttribute("aria-valuenow", "600");
    expect(localStorage.getItem("canvas-width")).toBe("600");
    fireEvent.keyDown(edge, { key: "ArrowRight" });
    expect(edge).toHaveAttribute("aria-valuenow", "584");

    typeInto("xin chào");
    const field = editor();
    fireEvent.click(screen.getByRole("tab", { name: vi.canvas.tabs.activity }));
    expect(screen.getByTestId("conversation-activity")).toBe(activity);
    expect(activity).toBeVisible();
    expect(field).not.toBeVisible();
    expect(field).toHaveValue("xin chào");
    fireEvent.click(screen.getByRole("tab", { name: vi.canvas.tabs.canvas }));
    expect(editor()).toBe(field);
  });

  it("keeps the open canvas and its typing as the window crosses 1101 px both ways", async () => {
    await openChat(1440);
    await openNote();
    typeInto("đang gõ");
    const field = editor();

    resize(1000);
    await landed();
    expect(screen.queryByRole("tablist")).toBeNull();
    expect(main()).toHaveAttribute("inert");
    expect(editor()).toBe(field);
    expect(field).toHaveValue("đang gõ");

    resize(1440);
    await landed();
    expect(screen.getByRole("tablist")).toBeInTheDocument();
    expect(main()).not.toHaveAttribute("inert");
    expect(editor()).toBe(field);
    // A panel that went away would have handed its typing to a save.
    expect(sent(backend, "PUT")).toEqual([]);
  });

  it("makes a canvas from the list and opens its name to type over", async () => {
    await openChat(1440);
    fireEvent.click(canvasButton());
    await landed();

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.newCanvas }));
    await landed();
    await landed();

    const made = backend.requests.filter((request) => request.method === "POST" && request.path === "/artifacts");
    expect(made.map((request) => request.body)).toEqual([
      { title: vi.canvas.untitled, kind: "markdown", content: "", conversation_id: "c1" },
    ]);
    expect(screen.getByRole("textbox", { name: vi.canvas.rename })).toHaveFocus();
  });
});

describe("the canvas dock below 1101 px", () => {
  it("covers the chat column, and Escape saves the typing, closes it and gives focus back", async () => {
    backend.runs = [fakeRun({ conversation_id: "c1", summary: "Đã xong" })];
    localStorage.setItem("conversation-activity.expanded", "1");
    await openChat(1000);
    const strip = screen.getByTestId("conversation-activity");

    fireEvent.click(canvasButton());
    await landed();
    expect(screen.queryByRole("tablist")).toBeNull();
    expect(screen.queryByRole("separator")).toBeNull();
    expect(main()).toHaveAttribute("inert");
    fireEvent.click(screen.getByRole("button", { name: /Ghi chú/ }));
    await landed();
    typeInto("xin chào");

    fireEvent.keyDown(document.body, { key: "Escape" });
    await landed();
    await landed();

    expect(sent(backend, "PUT").map((request) => request.body)).toEqual([typedAt("xin chào")]);
    expect(screen.queryByRole("region", { name: vi.canvas.button })).toBeNull();
    expect(main()).not.toHaveAttribute("inert");
    expect(canvasButton()).toHaveFocus();
    // The strip under the cover was not the topmost layer, so it stays as the person left it.
    expect(within(strip).getByRole("button", { name: vi.conversationActivity.collapse })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(localStorage.getItem("conversation-activity.expanded")).toBe("1");
  });

  it("goes back to the chat from the covering list", async () => {
    await openChat(1000);
    fireEvent.click(canvasButton());
    await landed();
    const back = screen.getByRole("button", { name: vi.canvas.backToChat });
    expect(back).toHaveFocus();

    fireEvent.click(back);
    await landed();

    expect(screen.queryByRole("button", { name: vi.canvas.backToChat })).toBeNull();
    expect(main()).not.toHaveAttribute("inert");
    expect(canvasButton()).toHaveFocus();
  });

  it("closes the drawer opened over the canvas before the canvas", async () => {
    for (let n = 3; n <= 8; n++) backend.create({ title: `Cuộc ${n}` });
    await openChat(390);
    fireEvent.click(canvasButton());
    await landed();
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const drawer = screen.getByRole("navigation", { hidden: true });
    expect(drawer).not.toHaveAttribute("inert");

    fireEvent.keyDown(document.body, { key: "Escape" });
    await landed();
    expect(drawer).toHaveAttribute("inert");
    expect(screen.getByRole("region", { name: vi.canvas.button })).toBeInTheDocument();

    fireEvent.keyDown(document.body, { key: "Escape" });
    await landed();
    expect(screen.queryByRole("region", { name: vi.canvas.button })).toBeNull();
  });
});

describe("the canvas dock across conversations", () => {
  it("closes as another conversation opens, and the typing left behind is saved", async () => {
    await openChat(1440);
    await openNote();
    typeInto("trước");

    fireEvent.click(conversation("Hai"));
    expect(editor()).toBeNull();
    expect(screen.queryByRole("tablist")).toBeNull();
    await landed();
    await landed();

    expect(sent(backend, "PUT").map((request) => request.body)).toEqual([typedAt("trước")]);
    expect(backend.canvas.content("a1")).toBe("trước");
    expect(layout()).toHaveClass("with-activity");
  });

  it("tells in the chat of a save that failed after the switch, until dismissed", async () => {
    await openChat(1440);
    await openNote();
    typeInto("không lưu được");
    backend.canvas.refuseNext("PUT", 422);

    fireEvent.click(conversation("Hai"));
    await landed();
    await landed();

    const told = screen.getByText(vi.canvas.handoffFailed("Ghi chú", true)).closest("[role=alert]") as HTMLElement;
    expect(main()).toContainElement(told);
    expect(localStorage.getItem("canvas-draft:a1")).toContain("không lưu được");
    fireEvent.click(within(told).getByRole("button", { name: vi.canvas.dismiss }));
    expect(screen.queryByText(vi.canvas.handoffFailed("Ghi chú", true))).toBeNull();
  });
});

describe("canvas drafts on this device", () => {
  it("drops the ones older than 30 days as the app starts", async () => {
    const draft = (id: string, age: number) =>
      JSON.stringify({ artifact_id: id, base_version: 1, base: "", text: "nháp", saved_at: Date.now() - age, sent: [] });
    localStorage.setItem("canvas-draft:a9", draft("a9", 31 * DAY));
    localStorage.setItem("canvas-draft:a8", draft("a8", 29 * DAY));
    screenAt(1440);

    render(<App />);
    await landed();

    expect(localStorage.getItem("canvas-draft:a9")).toBeNull();
    expect(localStorage.getItem("canvas-draft:a8")).not.toBeNull();
  });
});
