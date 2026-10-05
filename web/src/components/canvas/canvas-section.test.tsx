import { act, fireEvent, render, screen, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { vi } from "../../i18n/vi";
import { saveInBackground } from "../../lib/canvas-handoff";
import { NOTE, SHOP } from "../../test/canvas-dock-hook";
import { landed, sent, startServer, stopServer } from "../../test/canvas-hook";
import { leftCanvas } from "../../test/canvas-left";
import { editor, typeInto } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";
import { CanvasSection } from "./canvas-section";

const { canvas } = vi;
const name = (id: string) => id;

let backend: FakeBackend;

beforeEach(() => {
  backend = startServer();
  backend.canvas.add({ title: "Kế hoạch" });
});

afterEach(stopServer);

/** The section with no canvas named and nowhere to go, unless `over` says otherwise. */
const section = (over: Partial<ComponentProps<typeof CanvasSection>> = {}) => (
  <CanvasSection
    connected
    agentName={name}
    onOpenCanvas={() => undefined}
    conversations={[]}
    onOpenConversation={() => undefined}
    {...over}
  />
);

const lists = () => backend.requests.filter((r) => r.path.startsWith("/artifacts?")).map((r) => r.path);
const rows = () => screen.queryAllByTestId("canvas-library-row");
const back = () => screen.queryByRole("button", { name: canvas.back });
const page = () => document.querySelector(".canvas-page");

describe("the canvas section of the manage screen", () => {
  it("shows the library, and asks about no conversation's canvases", async () => {
    render(section());
    await landed();

    expect(rows()).toHaveLength(1);
    expect(rows()[0]).toHaveTextContent("Kế hoạch");
    expect(lists()).toEqual(["/artifacts?limit=200"]);
    expect(backend.requests.some((r) => r.path.includes("conversation"))).toBe(false);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(back()).toBeNull();
    expect(page()).toBeNull();
  });

  // A canvas left for another screen hands its last save on; this is where the person may be by then.
  it("says above the library that a save left behind did not land, until the person puts the line away", async () => {
    render(section());
    await landed();

    await act(() => saveInBackground(leftCanvas("a9", async () => null)));

    const notice = screen.getByRole("alert");
    expect(notice).toHaveTextContent(canvas.handoffFailed(canvas.untitled, true));
    const library = screen.getByTestId("canvas-library");
    expect(notice.compareDocumentPosition(library) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(library).not.toContainElement(notice);

    fireEvent.click(within(notice).getByRole("button", { name: canvas.dismiss }));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(rows()).toHaveLength(1);
  });

  // That a message went before its canvas was saved is said in the chat it went in, nowhere else.
  it("says nothing of a message sent before its canvas was saved", async () => {
    render(section());
    await landed();
    await act(() => saveInBackground(leftCanvas("a9", async () => null)));

    expect(screen.queryByText(canvas.sentUnsaved)).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("reads the library again when the stream comes back", async () => {
    const view = render(section());
    await landed();

    view.rerender(section({ connected: false }));
    view.rerender(section());
    await landed();

    expect(lists()).toHaveLength(2);
  });

  it("opens the canvas whose name is clicked in the library", async () => {
    const opened: (string | null)[] = [];
    backend.canvas.add({ id: NOTE, title: "Ghi chú" });
    render(section({ onOpenCanvas: (id) => opened.push(id) }));
    await landed();

    fireEvent.click(screen.getByRole("button", { name: "Ghi chú" }));

    expect(opened).toEqual([NOTE]);
  });
});

describe("the canvas the address names", () => {
  beforeEach(() => {
    backend.canvas.add({ id: NOTE, title: "Ghi chú", content: "a" });
    backend.canvas.add({ id: SHOP, title: "Mua sắm", content: "b" });
  });

  // An address is words anyone can type: only what the server could have named is asked of it.
  it.each([
    ["a1"],
    ["0123456789AB"],
    ["0123456789abc"],
    ["0123456789a"],
    ["..%2F..%2Fsettings"],
    ["0123456789ab?x=1"],
    [""],
  ])("shows the library for %j, which is no canvas's id, and asks the server nothing about it", async (bad) => {
    render(section({ canvasId: bad }));
    await landed();

    expect(rows()).toHaveLength(3);
    expect(page()).toBeNull();
    expect(back()).toBeNull();
    expect(backend.requests.map((r) => r.path).sort()).toEqual(["/artifacts/usage", "/artifacts?limit=200"]);
  });

  it("is shown on its page instead of the library, with the way back above it", async () => {
    const opened: (string | null)[] = [];
    render(section({ canvasId: NOTE, onOpenCanvas: (id) => opened.push(id) }));
    await landed();

    expect(editor()?.value).toBe("a");
    expect(rows()).toEqual([]);
    expect(lists()).toEqual([]);
    expect(page()).not.toBeNull();
    expect(page()).not.toContainElement(back());

    fireEvent.click(back() as HTMLElement);
    expect(opened).toEqual([null]);
  });

  it("is read anew when the address names another, and nothing typed in the first is lost", async () => {
    const view = render(section({ canvasId: NOTE }));
    await landed();
    typeInto("ab");

    view.rerender(section({ canvasId: SHOP }));
    await landed();

    expect(editor()?.value).toBe("b");
    expect(backend.canvas.content(NOTE)).toBe("ab");
    expect(sent(backend, "PUT", SHOP)).toEqual([]);
  });

  it("shows what was written to it while the stream was down, once the stream is back", async () => {
    const view = render(section({ canvasId: NOTE }));
    await landed();
    view.rerender(section({ canvasId: NOTE, connected: false }));
    // With the stream down, the server's news of this write reaches nobody.
    const stream = backend.canvas.onEvent;
    backend.canvas.onEvent = null;
    backend.canvas.write(NOTE, "viết lúc mất kết nối");
    backend.canvas.onEvent = stream;
    await landed();
    expect(editor()?.value).toBe("a");

    view.rerender(section({ canvasId: NOTE }));
    await landed();

    expect(editor()?.value).toBe("viết lúc mất kết nối");
  });
});

describe("a save that fails after its page was left", () => {
  beforeEach(() => {
    backend.canvas.add({ id: NOTE, title: "Ghi chú", content: "a" });
    backend.canvas.add({ id: SHOP, title: "Mua sắm", content: "b" });
  });

  const notice = () => screen.getByRole("alert");
  const failed = canvas.handoffFailed("Ghi chú", true);

  /** The page of the first canvas, left for `next` with words the server then refuses. */
  async function leftUnsaved(next: string | undefined) {
    const view = render(section({ canvasId: NOTE }));
    await landed();
    typeInto("ab");
    backend.canvas.refuseNext("PUT", 503);
    view.rerender(section({ canvasId: next }));
    await landed();
    return view;
  }

  it("is said above the library the person went back to", async () => {
    await leftUnsaved(undefined);

    expect(notice()).toHaveTextContent(failed);
    const library = screen.getByTestId("canvas-library");
    expect(notice().compareDocumentPosition(library) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(backend.canvas.content(NOTE)).toBe("a");
    expect(rows()).toHaveLength(3);
  });

  it("is said above the canvas the person went on to, and stays through the next move", async () => {
    const view = await leftUnsaved(SHOP);

    expect(notice()).toHaveTextContent(failed);
    expect(notice().compareDocumentPosition(back() as Element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(editor()?.value).toBe("b");

    backend.canvas.add({ id: "0000000000dd", title: "Ba", content: "c" });
    view.rerender(section({ canvasId: "0000000000dd" }));
    await landed();
    expect(notice()).toHaveTextContent(failed);
    expect(editor()?.value).toBe("c");

    view.rerender(section());
    await landed();
    expect(notice()).toHaveTextContent(failed);

    fireEvent.click(within(notice()).getByRole("button", { name: canvas.dismiss }));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  // The person deleted the canvas themselves: a save that finds it gone has failed at nothing.
  it("is not said of a canvas deleted from the library before the save got there", async () => {
    vitest.spyOn(window, "confirm").mockReturnValue(true);
    const view = render(section({ canvasId: NOTE }));
    await landed();
    typeInto("ab");
    const release = backend.canvas.holdNext("PUT");
    view.rerender(section());
    await landed();
    expect(sent(backend, "PUT", NOTE)).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: canvas.deleteLabel("Ghi chú") }));
    await landed();
    expect(rows()).toHaveLength(2);
    await act(async () => {
      await release();
    });
    await landed();

    expect(screen.queryByRole("alert")).toBeNull();
    expect(rows()).toHaveLength(2);
  });
});
