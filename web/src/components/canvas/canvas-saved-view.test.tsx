import { act, fireEvent, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import { errorReport } from "../../lib/error-report";
import type { FrameError } from "../../lib/frame-messages";
import type { SendResult } from "../../lib/send-result";
import { landed, startServer, stopServer, wait } from "../../test/canvas-hook";
import { openPanel, typeInto, versionLine } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";
import { SAMPLES } from "../../test/fake-canvas-kinds";
import { RELOAD_DELAY_MS } from "./canvas-frame";
import { CanvasPanel, type CanvasPanelProps } from "./canvas-panel";

const { page, pageErrors } = vi.canvas;

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
  vitest.setSystemTime(new Date("2026-10-02T03:05:00Z"));
});

afterEach(stopServer);

const FIRST: FrameError = { message: "Uncaught ReferenceError: dem is not defined", source: "", line: 12, column: 3 };
const SECOND: FrameError = { message: "Uncaught TypeError: nut is null", source: "", line: 4, column: 9 };
const NEWER = `${SAMPLES.html.content}<p>Bản hai</p>\n`;

const frame = () => document.querySelector("iframe.canvas-frame") as HTMLIFrameElement;
const pictures = () => [...document.querySelectorAll<HTMLImageElement>("img.canvas-picture")];
const picture = () => pictures()[0] ?? null;
const errors = () => screen.queryByRole("group", { name: pageErrors.group });
const count = () => errors()?.querySelector(".canvas-errors-count")?.textContent ?? null;
const listed = () => [...(errors()?.querySelectorAll(".canvas-error-message") ?? [])].map((each) => each.textContent);

/** A window says `error` went wrong, as the browser delivers it from a sandboxed frame. */
function reports(error: FrameError, source: Window | null = frame().contentWindow) {
  act(() => {
    window.dispatchEvent(
      Object.assign(new Event("message"), { source, origin: "null", data: { type: "canvas-error", ...error } }),
    );
  });
}

/** The page says `times` things went wrong, one after another, after `first` if it says that before them. */
function floods(times: number, first?: unknown) {
  const from = { source: frame().contentWindow, origin: "null", ports: [] };
  act(() => {
    if (first !== undefined) window.dispatchEvent(Object.assign(new Event("message"), { ...from, data: first }));
    for (let n = 1; n <= times; n++) {
      const data = { type: "canvas-error", ...FIRST, message: `lỗi ${n}` };
      window.dispatchEvent(Object.assign(new Event("message"), { ...from, data }));
    }
  });
}

/** The page says `data`, which is no report, to the app's window `times` over. */
function says(times: number, data: unknown) {
  const from = { source: frame().contentWindow, origin: "null", ports: [] };
  act(() => {
    for (let n = 0; n < times; n++) window.dispatchEvent(Object.assign(new Event("message"), { ...from, data }));
  });
}

/** A chat's send that takes every message. */
const taking = () => vitest.fn<NonNullable<CanvasPanelProps["onAsk"]>>(async (): Promise<SendResult> => ({ status: "sent" }));

/** An agent's page beside a chat whose send takes every message. */
async function openPage(overrides: Partial<CanvasPanelProps> = {}) {
  backend.canvas.add({ ...SAMPLES.html, agent_id: "ming" });
  const onAsk = taking();
  await openPanel({ onAsk, ...overrides });
  return onAsk;
}

const sendButton = () => within(errors() as HTMLElement).getByRole("button", { name: pageErrors.send }) as HTMLButtonElement;

/** The agent writes the page again; the panel reads it, and the frame still shows the one before. */
async function agentWrites() {
  act(() => {
    backend.canvas.write("a1", NEWER, { author: "agent:ming" });
  });
  await landed();
}

async function send() {
  fireEvent.click(sendButton());
  await landed();
}

/** The activity stream drops and comes back, and the panel is told of each. */
async function streamReturns(view: { rerender(ui: ReactElement): void; props: CanvasPanelProps }) {
  view.rerender(<CanvasPanel {...view.props} connected={false} />);
  await landed();
  view.rerender(<CanvasPanel {...view.props} connected />);
  await landed();
}

describe("what the page of a canvas reports, in the panel", () => {
  it("lists what the page itself says, and nothing another window says", async () => {
    const onAsk = await openPage();
    expect(errors()).toBeNull();

    reports(FIRST, window);
    expect(errors()).toBeNull();

    reports(FIRST);
    reports(SECOND);

    expect(count()).toBe(pageErrors.count(2));
    fireEvent.click(within(errors() as HTMLElement).getByRole("button", { name: pageErrors.show }));
    expect(listed()).toEqual([FIRST.message, SECOND.message]);
    expect(onAsk).not.toHaveBeenCalled();
  });

  it("sends the errors as those of the version the page was put up for, while a newer one waits its second", async () => {
    const onAsk = await openPage();
    await agentWrites();
    expect(versionLine()).toContain("v2");

    reports(FIRST);
    await send();

    expect(onAsk.mock.calls).toEqual([[{ artifact_id: "a1", selection: null }, errorReport("Trang hẹn giờ", 1, [FIRST])]]);
    expect(screen.getByText(pageErrors.sent(1))).toBeInTheDocument();
  });

  it("forgets what a page said once the newer version is put up, and counts the new page's from none", async () => {
    const onAsk = await openPage();
    const old = frame();
    reports(FIRST);
    expect(count()).toBe(pageErrors.count(1));

    await agentWrites();
    expect(count()).toBe(pageErrors.count(1));
    wait(RELOAD_DELAY_MS);

    expect(frame()).not.toBe(old);
    expect(errors()).toBeNull();

    reports(SECOND);
    expect(count()).toBe(pageErrors.count(1));
    await send();
    expect(onAsk.mock.calls).toEqual([[{ artifact_id: "a1", selection: null }, errorReport("Trang hẹn giờ", 2, [SECOND])]]);
  });

  it("lets the errors be sent again after a new page reports, though the ones before were sent", async () => {
    const onAsk = await openPage();
    reports(FIRST);
    await send();
    const button = () => within(errors() as HTMLElement).getByRole("button", { name: pageErrors.send }) as HTMLButtonElement;
    expect(button().disabled).toBe(true);

    await agentWrites();
    wait(RELOAD_DELAY_MS);
    reports(SECOND);

    expect(button().disabled).toBe(false);
    expect(screen.queryByText(pageErrors.sent(1))).toBeNull();
    expect(onAsk).toHaveBeenCalledTimes(1);
  });

  it("forgets what a page said when it is taken out for moving to another address", async () => {
    await openPage();
    reports(FIRST);
    expect(count()).toBe(pageErrors.count(1));

    fireEvent.load(frame());
    expect(count()).toBe(pageErrors.count(1));
    fireEvent.load(frame());

    expect(screen.getByText(page.navigated)).toBeInTheDocument();
    expect(errors()).toBeNull();
  });

  it("counts every report the page makes and keeps the newest five to list", async () => {
    await openPage();

    for (let n = 1; n <= 7; n++) reports({ ...FIRST, message: `lỗi ${n}` });

    expect(count()).toBe(pageErrors.count(7));
    fireEvent.click(within(errors() as HTMLElement).getByRole("button", { name: pageErrors.show }));
    expect(listed()).toEqual(["lỗi 3", "lỗi 4", "lỗi 5", "lỗi 6", "lỗi 7"]);
  });

  it("stops counting at fifty, says the page reported more, and lists the newest five of the fifty", async () => {
    await openPage();

    floods(10_000);

    expect(count()).toBe(pageErrors.count(50, true));
    expect(count()).toContain("50+");
    fireEvent.click(within(errors() as HTMLElement).getByRole("button", { name: pageErrors.show }));
    expect(listed()).toEqual(["lỗi 46", "lỗi 47", "lỗi 48", "lỗi 49", "lỗi 50"]);
  });

  it("does not say the page reported more for the fifty reports it was heard out on short of one", async () => {
    await openPage();

    floods(49);

    expect(count()).toBe(pageErrors.count(49));
    expect(count()).not.toContain("+");
  });

  it("says the page reported more when one of the fifty was its reporter's hello, and counts the forty-nine", async () => {
    await openPage();

    floods(10_000, { type: "canvas-hello" });

    expect(count()).toBe(pageErrors.count(49, true));
    expect(count()).toContain("49+");
    fireEvent.click(within(errors() as HTMLElement).getByRole("button", { name: pageErrors.show }));
    expect(listed()).toEqual(["lỗi 45", "lỗi 46", "lỗi 47", "lỗi 48", "lỗi 49"]);
  });

  it("says the page is no longer heard once it has said fifty things, though none was a report", async () => {
    await openPage();

    says(49, "không phải lời báo");
    expect(errors()).toBeNull();
    says(1, "không phải lời báo");

    expect(errors()?.textContent).toBe(pageErrors.unheard);
    // A report it makes now is one of those no longer heard.
    reports(FIRST);
    expect(errors()?.textContent).toBe(pageErrors.unheard);

    await agentWrites();
    wait(RELOAD_DELAY_MS);
    expect(errors()).toBeNull();
  });

  it("hears the page put up next from none, and does not say of it what it said of the one before", async () => {
    await openPage();
    floods(10_000);
    expect(count()).toContain("50+");

    await agentWrites();
    wait(RELOAD_DELAY_MS);
    reports(SECOND);

    expect(count()).toBe(pageErrors.count(1));
    expect(count()).not.toContain("+");
  });

  it("puts the page up again when the activity stream comes back, with nothing listed against it", async () => {
    backend.canvas.add({ ...SAMPLES.html, agent_id: "ming" });
    const view = await openPanel();
    const first = frame();
    reports(FIRST);

    await streamReturns(view);

    expect(frame()).not.toBe(first);
    expect(frame().getAttribute("src")).toBe("/api/artifacts/a1/render");
    expect(errors()).toBeNull();
  });

  it("keeps the errors from being sent while the chat cannot take a message, and says why", async () => {
    const onAsk = await openPage({ askDisabled: "busy" });

    reports(FIRST);

    expect(sendButton().disabled).toBe(true);
    expect(within(errors() as HTMLElement).getByText(vi.canvas.ask.busy)).toBeInTheDocument();
    expect(onAsk).not.toHaveBeenCalled();
  });

  it("does not send the errors when what was typed could not be saved, and says so", async () => {
    backend.canvas.add(SAMPLES.html);
    const onAsk = taking();
    await openPanel({ onAsk });
    typeInto(NEWER);
    backend.canvas.refuseNext("PUT", 422);
    fireEvent.click(within(screen.getByRole("group", { name: vi.canvas.mode })).getAllByRole("button")[0]);
    await landed();
    expect(screen.getByText(page.savedVersion(1))).toBeInTheDocument();

    reports(FIRST);
    await send();

    expect(within(errors() as HTMLElement).getByRole("alert").textContent).toBe(pageErrors.notSaved);
    expect(onAsk).not.toHaveBeenCalled();
    expect(sendButton().disabled).toBe(false);
  });
});

describe("what a drawing reports, in the panel", () => {
  // The picture is told apart by its version and the list by its page, and both count from one.
  it("stays one picture however often the panel is drawn again", async () => {
    backend.canvas.add({ ...SAMPLES.svg, agent_id: "ming" });
    const { rerender, props } = await openPanel();

    rerender(<CanvasPanel {...props} />);
    rerender(<CanvasPanel {...props} />);

    expect(pictures().map((each) => each.getAttribute("src"))).toEqual(["/api/artifacts/a1/raw?version=1"]);
  });

  it("lists a drawing the browser cannot draw though the server holds it, for the agent to mend", async () => {
    backend.canvas.add({ ...SAMPLES.svg, agent_id: "ming" });
    const onAsk = vitest.fn<NonNullable<CanvasPanelProps["onAsk"]>>(async (): Promise<SendResult> => ({ status: "sent" }));
    await openPanel({ onAsk });
    expect(errors()).toBeNull();

    fireEvent.error(picture() as HTMLImageElement);
    await landed();

    expect(screen.getByText(page.imageBroken)).toBeInTheDocument();
    expect(pictures()).toEqual([]);
    expect(count()).toBe(pageErrors.count(1));
    await send();
    const invalid = { message: page.svgInvalid, source: "", line: 0, column: 0 };
    expect(onAsk.mock.calls).toEqual([[{ artifact_id: "a1", selection: null }, errorReport("Hình tròn", 1, [invalid])]]);
  });

  it("draws the next version as a picture of its own, with nothing listed against it", async () => {
    backend.canvas.add({ ...SAMPLES.svg, agent_id: "ming" });
    await openPanel();
    fireEvent.error(picture() as HTMLImageElement);
    await landed();
    expect(count()).toBe(pageErrors.count(1));

    act(() => {
      backend.canvas.write("a1", SAMPLES.svg.content.replace('r="40"', 'r="20"'), { author: "agent:ming" });
    });
    await landed();

    expect(pictures().map((each) => each.getAttribute("src"))).toEqual(["/api/artifacts/a1/raw?version=2"]);
    expect(errors()).toBeNull();
  });

  it("reads the canvas again when the version it draws is gone, and draws the one that took its place", async () => {
    backend.canvas.add({ ...SAMPLES.svg, agent_id: "ming" });
    await openPanel();
    // The agent wrote again and the first version was folded into the second, and no word of it came.
    backend.canvas.onEvent = null;
    backend.canvas.write("a1", SAMPLES.svg.content.replace('r="40"', 'r="20"'), { author: "agent:ming" });
    backend.canvas.forget("a1", 1);

    fireEvent.error(picture() as HTMLImageElement);
    await landed();

    expect(versionLine()).toContain("v2");
    expect(pictures().map((each) => each.getAttribute("src"))).toEqual(["/api/artifacts/a1/raw?version=2"]);
    expect(errors()).toBeNull();
  });

  it("draws a picture that did not arrive again when the activity stream comes back", async () => {
    backend.canvas.add({ ...SAMPLES.svg, agent_id: "ming" });
    const view = await openPanel();
    backend.canvas.loseNext("GET /artifacts/a1/raw");

    fireEvent.error(picture() as HTMLImageElement);
    await landed();
    expect(screen.getByText(page.imageWaiting)).toBeInTheDocument();
    expect(pictures()).toEqual([]);

    await streamReturns(view);

    expect(screen.queryByText(page.imageWaiting)).toBeNull();
    expect(pictures().map((each) => each.getAttribute("src"))).toEqual(["/api/artifacts/a1/raw?version=1"]);
    expect(errors()).toBeNull();
  });
});
