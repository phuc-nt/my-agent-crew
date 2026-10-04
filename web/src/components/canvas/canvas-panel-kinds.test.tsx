import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import type { SendResult } from "../../lib/send-result";
import { askButton, bar, openBox, questionBox } from "../../test/canvas-ask";
import { landed, sent, startServer, stopServer } from "../../test/canvas-hook";
import { historyShown } from "../../test/canvas-history";
import { pickIn } from "../../test/canvas-pick";
import { editor, mode, openPanel, typeInto } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";
import { SAMPLES } from "../../test/fake-canvas-kinds";

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
  vitest.setSystemTime(new Date("2026-10-02T03:05:00Z"));
});

afterEach(stopServer);

const frame = () => document.querySelector("iframe.canvas-frame");
const picture = () => document.querySelector("img.canvas-picture");
const modeButtons = () => within(screen.getByRole("group", { name: vi.canvas.mode })).getAllByRole("button");
const viewButton = () => modeButtons()[0];
const editButton = () => modeButtons()[1];
const openPage = () => screen.queryByRole("button", { name: vi.canvas.page.open }) as HTMLButtonElement | null;
const savedNote = () => document.querySelector(".canvas-saved-note")?.textContent ?? null;
const typed = `${SAMPLES.html.content}<p>Mới</p>\n`;
const asking = () => vitest.fn(async (): Promise<SendResult> => ({ status: "sent" }));

describe("a canvas shown as a page", () => {
  it("opens an agent's HTML as the page, in a frame that runs it apart from the app", async () => {
    backend.canvas.add({ ...SAMPLES.html, agent_id: "ming" });

    await openPanel();

    expect(mode()).toBe(vi.canvas.view);
    expect(editor()).toBeNull();
    expect(frame()?.getAttribute("sandbox")).toBe("allow-scripts");
    expect(frame()?.getAttribute("src")).toBe("/api/artifacts/a1/render");
    expect(frame()?.getAttribute("title")).toBe("Trang hẹn giờ");
    expect(frame()?.getAttribute("referrerpolicy")).toBe("no-referrer");
  });

  it("opens HTML just made here to edit in the code face, whoever wrote it", async () => {
    backend.canvas.add({ ...SAMPLES.html, agent_id: "ming" });
    await openPanel({ created: true });

    expect(mode()).toBe(vi.canvas.edit);
    expect(editor()).toHaveClass("canvas-editor", "code");
    expect(editor()?.getAttribute("spellcheck")).toBe("false");
    expect(frame()).toBeNull();
  });

  it("draws an agent's Mermaid diagram as a page too", async () => {
    backend.canvas.add({ ...SAMPLES.mermaid, agent_id: "ming" });

    await openPanel();

    expect(frame()?.getAttribute("src")).toBe("/api/artifacts/a1/render");
    expect(openPage()).not.toBeNull();
  });

  it("turns to the page at once when nothing is unsaved, and sends nothing", async () => {
    backend.canvas.add(SAMPLES.html);
    await openPanel();
    expect(mode()).toBe(vi.canvas.edit);

    fireEvent.click(viewButton());
    // In the click itself: there is no save to wait for, and none is asked after.
    expect(mode()).toBe(vi.canvas.view);
    expect(viewButton().getAttribute("aria-busy")).toBeNull();
    expect(frame()).not.toBeNull();
    await landed();

    expect(mode()).toBe(vi.canvas.view);
    expect(frame()).not.toBeNull();
    expect(sent(backend, "PUT")).toHaveLength(0);
    expect(savedNote()).toBeNull();
  });

  it("saves what was typed before turning to the page, and says so on the View button meanwhile", async () => {
    backend.canvas.add(SAMPLES.html);
    await openPanel();
    typeInto(typed);
    const release = backend.canvas.holdNext("PUT", "reply");

    fireEvent.click(viewButton());
    await landed();

    expect(viewButton().getAttribute("aria-busy")).toBe("true");
    expect(viewButton().textContent).toBe(vi.canvas.status.saving);
    expect(mode()).toBe(vi.canvas.edit);
    expect(editor()?.value).toBe(typed);
    expect(frame()).toBeNull();

    await act(async () => {
      await release();
    });
    await landed();

    expect(mode()).toBe(vi.canvas.view);
    expect(viewButton().getAttribute("aria-busy")).toBeNull();
    expect(viewButton().textContent).toBe(vi.canvas.view);
    expect(backend.canvas.content("a1")).toBe(typed);
    expect(frame()).not.toBeNull();
    expect(savedNote()).toBeNull();
  });

  it("keeps the last click: Edit pressed while the save is out stays in Edit when it lands", async () => {
    backend.canvas.add(SAMPLES.html);
    await openPanel();
    typeInto(typed);
    const release = backend.canvas.holdNext("PUT", "reply");
    fireEvent.click(viewButton());
    await landed();

    fireEvent.click(editButton());
    expect(viewButton().getAttribute("aria-busy")).toBeNull();
    await act(async () => {
      await release();
    });
    await landed();

    expect(mode()).toBe(vi.canvas.edit);
    expect(editor()?.value).toBe(typed);
    expect(frame()).toBeNull();
  });

  it("keeps the history open when it was opened while the save was out", async () => {
    backend.canvas.add(SAMPLES.html);
    await openPanel();
    typeInto(typed);
    const release = backend.canvas.holdNext("PUT", "reply");
    fireEvent.click(viewButton());
    await landed();

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.history }));
    await act(async () => {
      await release();
    });
    await landed();

    expect(historyShown()).toBe(true);
    expect(mode()).toBe(vi.canvas.edit);
    expect(viewButton().textContent).toBe(vi.canvas.view);
  });

  it("shows the last saved version when the save was refused, and says the typing is not in it", async () => {
    backend.canvas.add(SAMPLES.html);
    await openPanel();
    typeInto(typed);
    backend.canvas.refuseNext("PUT", 422);

    fireEvent.click(viewButton());
    await landed();

    expect(mode()).toBe(vi.canvas.view);
    expect(frame()).not.toBeNull();
    expect(savedNote()).toBe(vi.canvas.page.savedVersion(1));
    expect(backend.canvas.content("a1")).toBe(SAMPLES.html.content);
  });

  it("opens the saved page in a new tab, and only once nothing is unsaved", async () => {
    backend.canvas.add(SAMPLES.html);
    await openPanel();
    const open = vitest.spyOn(window, "open").mockReturnValue(null);
    expect(openPage()?.disabled).toBe(false);

    typeInto(typed);
    expect(openPage()?.disabled).toBe(true);
    fireEvent.keyDown(editor() as HTMLTextAreaElement, { key: "s", ctrlKey: true });
    await landed();
    expect(openPage()?.disabled).toBe(false);

    fireEvent.click(openPage() as HTMLButtonElement);
    expect(open.mock.calls).toEqual([["/api/artifacts/a1/render", "_blank", "noopener,noreferrer"]]);
  });

  it("offers no page to open while the canvas is known by name only and not yet read", async () => {
    backend.canvas.add({ ...SAMPLES.html, agent_id: "ming" });
    const release = backend.canvas.holdNext("GET /artifacts/a1");
    await openPanel();
    // The stream names the canvas and its kind before the read has answered.
    act(() => {
      backend.canvas.write("a1", typed, { author: "agent:ming" });
    });
    await landed();

    expect(screen.getByRole("heading", { name: SAMPLES.html.title })).toBeTruthy();
    expect(frame()).toBeNull();
    expect(openPage()).toBeNull();

    await act(async () => {
      await release();
    });
    await landed();

    expect(frame()).not.toBeNull();
    expect(openPage()).not.toBeNull();
  });

  it("says the page has hidden characters, which the frame would run without showing", async () => {
    backend.canvas.add({ ...SAMPLES.html, agent_id: "ming", content: "<!doctype html>\n<p>a\u202eb</p>\n" });

    await openPanel();

    expect(mode()).toBe(vi.canvas.view);
    expect(frame()).not.toBeNull();
    expect(screen.getByRole("note").textContent).toBe(`${vi.canvas.hiddenChars} ${vi.canvas.hiddenCharsHint}`);
  });

  it("offers no page to open once the canvas is deleted", async () => {
    backend.canvas.add({ ...SAMPLES.html, agent_id: "ming" });
    await openPanel();
    expect(openPage()).not.toBeNull();

    act(() => {
      backend.canvas.remove("a1");
    });
    await landed();

    expect(openPage()).toBeNull();
    expect(screen.queryByRole("button", { name: vi.canvas.history })).toBeNull();
  });
});

describe("a canvas shown as a picture", () => {
  it("draws an agent's SVG from the saved version, with no page to open, and keeps it editable", async () => {
    backend.canvas.add({ ...SAMPLES.svg, agent_id: "ming" });

    await openPanel();

    expect(mode()).toBe(vi.canvas.view);
    expect(picture()?.getAttribute("src")).toBe("/api/artifacts/a1/raw?version=1");
    expect(picture()?.className).toBe("canvas-picture vector");
    expect(openPage()).toBeNull();
    expect(modeButtons().map((each) => each.textContent)).toEqual([vi.canvas.view, vi.canvas.edit]);
    expect(screen.getByRole("button", { name: vi.canvas.copy })).toBeTruthy();
  });

  it("shows an image only to look at, even when it was just made, with nothing to copy", async () => {
    backend.canvas.add(SAMPLES.image);

    await openPanel({ created: true });

    expect(modeButtons().map((each) => each.textContent)).toEqual([vi.canvas.view]);
    expect(mode()).toBe(vi.canvas.view);
    expect(editor()).toBeNull();
    expect(picture()?.getAttribute("src")).toBe("/api/artifacts/a1/raw?version=1");
    expect(picture()?.getAttribute("alt")).toBe("Biểu đồ.png");
    expect(picture()?.className).toBe("canvas-picture");
    expect(screen.queryByRole("button", { name: vi.canvas.copy })).toBeNull();
    expect(openPage()).toBeNull();
    expect(screen.queryByRole("group", { name: vi.canvas.pageErrors.group })).toBeNull();
  });
});

describe("asking about a passage of a canvas shown as what the server holds", () => {
  // A question box left open keeps its passage through a change of the selection, so it is the
  // turn to the page or the picture that must take the bar away.
  it.each([
    ["html", "Bắt đầu"],
    ["svg", "circle"],
    ["mermaid", "Xong"],
  ] as const)("drops the bar, and the box open in it, on the turn from the text of %s to what it shows", async (kind, needle) => {
    backend.canvas.add(SAMPLES[kind]);
    await openPanel({ onAsk: asking() });
    pickIn(editor() as HTMLTextAreaElement, needle);
    expect(askButton()).not.toBeNull();
    openBox();
    expect(questionBox()).not.toBeNull();

    fireEvent.click(viewButton());
    await landed();

    expect(mode()).toBe(vi.canvas.view);
    expect(bar()).toBeNull();
    expect(screen.queryByRole("textbox", { name: vi.canvas.ask.question })).toBeNull();
  });

  it("offers nothing to ask about a picture, which has no text to select", async () => {
    backend.canvas.add({ ...SAMPLES.image, agent_id: "ming" });

    await openPanel({ onAsk: asking() });

    expect(picture()).not.toBeNull();
    expect(bar()).toBeNull();
  });
});

describe("a kind the web does not know", () => {
  it("is shown as text in the code face", async () => {
    backend.canvas.add({ kind: "pdf", title: "Báo cáo", agent_id: "ming", content: "Trang 1\n" });

    await openPanel();

    expect(document.querySelector("pre.canvas-view.canvas-code")?.textContent).toContain("Trang 1");
    expect(frame()).toBeNull();
    expect(picture()).toBeNull();
  });
});
