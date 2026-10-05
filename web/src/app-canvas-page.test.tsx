import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { openChat, openNote, startApp } from "./test/canvas-app";
import { NOTE } from "./test/canvas-dock-hook";
import { landed, sent, stopServer } from "./test/canvas-hook";
import { editor } from "./test/canvas-panel";
import type { FakeBackend } from "./test/fake-backend";
import { screenAt } from "./test/screen-width";

const { canvas } = vi;

let backend: FakeBackend;

beforeEach(() => {
  backend = startApp();
  backend.canvas.add({ id: NOTE, title: "Sổ tay", content: "a", conversationIds: ["c2"] });
});

afterEach(stopServer);

/** The app as a link to `hash` opens it. */
async function openAt(hash: string) {
  screenAt(1440);
  window.location.hash = hash;
  render(<App />);
  await landed();
  await landed();
}

const manage = () => screen.getByRole("main", { name: vi.manage.label });
const rows = () => screen.queryAllByTestId("canvas-library-row");

describe("a canvas's own page in the app", () => {
  it("is where a link to it lands, and its way back leads to the library, whose rows lead to it again", async () => {
    await openAt(`#/manage/canvas/${NOTE}`);

    expect(within(manage()).getByRole("heading", { level: 2, name: canvas.tab })).toBeInTheDocument();
    expect(within(manage()).getByRole("heading", { level: 2, name: "Sổ tay" })).toBeInTheDocument();
    expect(editor()?.value).toBe("a");
    expect(rows()).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: canvas.back }));
    await landed();
    expect(window.location.hash).toBe("#/manage/canvas");
    expect(rows()).toHaveLength(2);
    expect(editor()).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Sổ tay" }));
    await landed();
    expect(window.location.hash).toBe(`#/manage/canvas/${NOTE}`);
    expect(editor()?.value).toBe("a");
  });

  it("names the conversations the canvas is used in by their titles, and opens the one clicked in the chat", async () => {
    await openAt(`#/manage/canvas/${NOTE}`);
    const used = document.querySelector(".canvas-page-used") as HTMLElement;
    expect(used.textContent).toBe(`${canvas.usedIn(1)}Hai`);

    fireEvent.click(within(used).getByRole("button", { name: "Hai" }));
    await landed();
    await landed();

    expect(window.location.hash).toBe("#/chat/c2");
    expect(screen.queryByRole("main", { name: vi.manage.label })).toBeNull();
    expect(screen.getByRole("textbox", { name: vi.composerPlaceholder })).toBeInTheDocument();
  });

  it("gives way to the library, id dropped from the address, when another part of the screen is chosen and come back from", async () => {
    await openAt(`#/manage/canvas/${NOTE}`);

    fireEvent.click(within(screen.getByRole("navigation", { name: vi.manage.nav })).getByRole("button", { name: vi.jobs }));
    await landed();
    expect(window.location.hash).toBe("#/manage/jobs");
    fireEvent.click(within(screen.getByRole("navigation", { name: vi.manage.nav })).getByRole("button", { name: canvas.tab }));
    await landed();

    expect(window.location.hash).toBe("#/manage/canvas");
    expect(rows()).toHaveLength(2);
  });

  // "a1" is a canvas the server has, under a name no server of ours gives: the address is not trusted.
  it("shows the library for a link that names what is no canvas's id, and asks the server nothing about it", async () => {
    await openAt("#/manage/canvas/a1");

    expect(rows()).toHaveLength(2);
    expect(screen.queryByRole("button", { name: canvas.back })).toBeNull();
    expect(sent(backend, "GET", "a1")).toEqual([]);
    expect(backend.requests.filter((r) => r.path.startsWith("/artifacts/")).map((r) => r.path)).toEqual(["/artifacts/usage"]);
  });

  it.each(["%", "%E0%A4%A", "%zz"])("shows the library, not a blank screen, for a link whose canvas is written %j", async (broken) => {
    await openAt(`#/manage/canvas/${broken}`);

    expect(rows()).toHaveLength(2);
    expect(screen.queryByRole("button", { name: canvas.back })).toBeNull();
    expect(backend.requests.filter((r) => r.path.startsWith("/artifacts/")).map((r) => r.path)).toEqual(["/artifacts/usage"]);
  });

  it("is one click from the canvas open beside a conversation, in a tab of its own", async () => {
    await openChat(1440);
    await openNote();
    const open = vitest.spyOn(window, "open").mockReturnValue(null);

    fireEvent.click(screen.getByRole("button", { name: canvas.openStandalone }));

    expect(open.mock.calls).toEqual([["#/manage/canvas/a1", "_blank", "noopener,noreferrer"]]);
    expect(window.location.hash).not.toContain("manage");
  });
});
