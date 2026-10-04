import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { useCanvasDock } from "../../hooks/use-canvas-dock";
import { vi } from "../../i18n/vi";
import { handoffOut } from "../../lib/canvas-handoff";
import { NOTE, SHOP } from "../../test/canvas-dock-hook";
import { landed, sent, startServer, stopServer } from "../../test/canvas-hook";
import { editor, typeInto } from "../../test/canvas-panel";
import type { FakeBackend } from "../../test/fake-backend";
import { CanvasPage } from "./canvas-page";
import { CanvasSection } from "./canvas-section";

const { canvas } = vi;
const name = (id: string) => (id === "coach" ? "HLV" : id);
const FILE = "workspace:coach/notes/ke-hoach.md";

let backend: FakeBackend;
/** Where the section asked to go, oldest first: a canvas's id, or null for the library. */
let moved: (string | null)[];
/** The conversations the page asked to open. */
let chats: string[];

beforeEach(() => {
  backend = startServer();
  backend.create({ title: "Một" });
  backend.create({ title: "Hai" });
  backend.canvas.add({ id: NOTE, title: "Ghi chú", content: "a", conversationIds: ["c1"] });
  backend.canvas.add({ id: SHOP, title: "Mua sắm", content: "b" });
  moved = [];
  chats = [];
});

afterEach(stopServer);

/** The canvas section as the app drives it: the address names the canvas, and a move rewrites it. */
function Manage({ start }: { start?: string }) {
  const [id, setId] = useState(start);
  return (
    <CanvasSection
      connected
      agentName={name}
      canvasId={id}
      onOpenCanvas={(next) => {
        moved.push(next);
        setId(next ?? undefined);
      }}
      conversations={[...backend.conversations.values()]}
      onOpenConversation={(conversationId) => chats.push(conversationId)}
    />
  );
}

async function openPage(id = NOTE) {
  const view = render(<Manage start={id} />);
  await landed();
  return view;
}

const back = () => screen.getByRole("button", { name: canvas.back });
const panel = () => document.querySelector(".canvas-panel");
const rows = () => screen.queryAllByTestId("canvas-library-row");
const used = () => document.querySelector(".canvas-page-used");
const usedButtons = () => within(used() as HTMLElement).getAllByRole("button").map((each) => each.textContent);
const focusWrites = () => backend.requests.filter((r) => r.method === "PUT" && r.path.endsWith("/canvas"));

describe("a canvas on a page of its own", () => {
  it("shows the canvas the address names in the panel a conversation shows it in, under a way back", async () => {
    await openPage();

    expect(screen.getByRole("heading", { name: "Ghi chú" })).toBeTruthy();
    expect(editor()?.value).toBe("a");
    expect(screen.queryByTestId("canvas-library")).toBeNull();
    expect(backend.requests.some((r) => r.path.startsWith("/artifacts?"))).toBe(false);
    expect(back().compareDocumentPosition(panel() as Element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(panel()?.closest(".canvas-page")).not.toBeNull();
  });

  // The page belongs to no conversation: nothing here can be said to an agent, or told to a chat.
  it("has nothing to ask an agent with, no page of its own to open, and tells no conversation what is open", async () => {
    backend.canvas.add({ id: "0000000000aa", title: "Trang", kind: "html", content: "<p>Chào</p>", agent_id: "coach" });
    await openPage("0000000000aa");

    expect(screen.getByRole("button", { name: canvas.page.open })).toBeTruthy();
    expect(screen.queryByRole("button", { name: canvas.openStandalone })).toBeNull();
    expect(screen.queryByRole("group", { name: canvas.ask.group })).toBeNull();
    expect(screen.queryByRole("button", { name: canvas.pageErrors.send })).toBeNull();
    expect(focusWrites()).toEqual([]);
    expect(backend.requests.some((r) => r.path.includes("/conversations"))).toBe(false);
  });

  it("goes back to the library at once with words unsaved, and their save goes on behind", async () => {
    await openPage();
    typeInto("ab");
    const release = backend.canvas.holdNext("PUT", "reply");

    fireEvent.click(back());

    // In the click itself: the save is not waited for.
    expect(moved).toEqual([null]);
    expect(panel()).toBeNull();
    expect(screen.getByTestId("canvas-library")).toBeTruthy();
    expect(handoffOut(NOTE)).toBe(true);

    await act(async () => {
      await release();
    });
    await landed();

    expect(sent(backend, "PUT", NOTE).map((r) => r.body)).toEqual([{ content: "ab", base_version: 1 }]);
    expect(backend.canvas.content(NOTE)).toBe("ab");
    expect(handoffOut(NOTE)).toBe(false);
    expect(rows()).toHaveLength(2);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("goes back to the library from the panel's own close and from its way to the list", async () => {
    await openPage();

    fireEvent.click(screen.getByRole("button", { name: canvas.close }));
    expect(moved).toEqual([null]);
    await landed();

    fireEvent.click(within(rows()[1]).getByRole("button", { name: "Ghi chú" }));
    expect(moved).toEqual([null, NOTE]);
    await landed();
    expect(editor()?.value).toBe("a");

    fireEvent.click(screen.getByRole("button", { name: canvas.toList }));
    expect(moved).toEqual([null, NOTE, null]);
    expect(panel()).toBeNull();
  });

  it("says a canvas that is not there is deleted, as the panel does, and keeps the way back", async () => {
    await openPage("0000000000ff");

    expect(screen.getByRole("alert").textContent).toBe(`${canvas.gone} ${canvas.goneHint}`);
    expect(used()).toBeNull();
    fireEvent.click(back());
    expect(moved).toEqual([null]);
  });

  it("says so when the canvas is deleted while it is open, and no longer names its conversations", async () => {
    await openPage();
    expect(used()).not.toBeNull();
    const reads = sent(backend, "GET", NOTE).length;

    act(() => backend.canvas.remove(NOTE));
    await landed();

    expect(screen.getByRole("alert").textContent).toBe(`${canvas.gone} ${canvas.goneHint}`);
    expect(used()).toBeNull();
    // A deletion is the whole news: there is nothing left to read.
    expect(sent(backend, "GET", NOTE)).toHaveLength(reads);
    expect(back()).toBeTruthy();
  });

  it("reads the canvas's file again, with no conversation to speak of", async () => {
    backend.canvas.add({ id: "0000000000bb", title: "Kế hoạch", content: "cũ", source: FILE });
    backend.canvas.files.put(FILE, "mới từ tệp");
    await openPage("0000000000bb");
    expect(document.querySelector(".canvas-source")?.textContent).toContain("HLV/notes/ke-hoach.md");

    fireEvent.click(screen.getByRole("button", { name: canvas.source.reimport }));
    await landed();
    await landed();

    expect(backend.canvas.content("0000000000bb")).toBe("mới từ tệp");
    expect(editor()?.value).toBe("mới từ tệp");
  });
});

describe("the conversations a canvas on its own page is used in", () => {
  it("names each under the panel, and opens the one clicked", async () => {
    backend.canvas.add({ id: "0000000000cc", title: "Chung", content: "x", conversationIds: ["c2", "c1"] });
    await openPage("0000000000cc");

    expect(used()?.firstElementChild?.textContent).toBe(canvas.usedIn(2));
    expect(usedButtons()).toEqual(["Hai", "Một"]);
    expect((panel() as Element).compareDocumentPosition(used() as Element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    fireEvent.click(within(used() as HTMLElement).getByRole("button", { name: "Một" }));
    expect(chats).toEqual(["c1"]);
  });

  it("calls a conversation with no name, or one this tab has not listed, by the start of its id", async () => {
    backend.create({ title: "" });
    backend.canvas.add({ id: "0000000000cc", title: "Chung", content: "x", conversationIds: ["c3", "9f8e7d6c5b4a"] });
    await openPage("0000000000cc");

    expect(usedButtons()).toEqual([canvas.conversationFallback("c3"), canvas.conversationFallback("9f8e7d6c5b4a")]);
    expect(canvas.conversationFallback("9f8e7d6c5b4a")).toBe("Hội thoại 9f8e7d");

    fireEvent.click(screen.getByRole("button", { name: "Hội thoại 9f8e7d" }));
    expect(chats).toEqual(["9f8e7d6c5b4a"]);
  });

  it("has no line for a canvas no conversation uses", async () => {
    await openPage(SHOP);

    expect(editor()?.value).toBe("b");
    expect(used()).toBeNull();
  });

  it("has no line when the read of it failed, though the panel has the canvas", async () => {
    // The panel reads first; the second read of the canvas is the page's own.
    const first = backend.canvas.holdNext(`GET /artifacts/${NOTE}`, "reply");
    backend.canvas.refuseNext(`GET /artifacts/${NOTE}`, 503);
    render(<Manage start={NOTE} />);
    await act(async () => {
      await first();
    });
    await landed();

    expect(sent(backend, "GET", NOTE)).toHaveLength(2);
    expect(editor()?.value).toBe("a");
    expect(used()).toBeNull();
  });

  it("reads them again when the stream says the canvas changed", async () => {
    await openPage(SHOP);
    expect(used()).toBeNull();

    act(() => {
      backend.canvas.canvases.get(SHOP)?.conversationIds.push("c2");
      backend.canvas.write(SHOP, "b!", { author: "agent:coach" });
    });
    await landed();

    expect(used()?.firstElementChild?.textContent).toBe(canvas.usedIn(1));
    expect(usedButtons()).toEqual(["Hai"]);
  });

  it("reads nothing again for news of another canvas", async () => {
    await openPage();
    const reads = sent(backend, "GET", NOTE).length;

    act(() => backend.canvas.write(SHOP, "b!", { author: "agent:coach" }));
    await landed();

    expect(sent(backend, "GET", NOTE)).toHaveLength(reads);
    expect(usedButtons()).toEqual(["Một"]);
  });
});

describe("the page and the dock it borrows", () => {
  /** The page alone, on a dock whose moves are watched. */
  function Alone({ id, stuck, watch }: { id: string; stuck?: boolean; watch: Record<string, () => void> }) {
    const dock = useCanvasDock(null, true, false);
    return (
      <CanvasPage
        id={id}
        connected
        dock={{ ...dock, ...watch, stuck: stuck ?? dock.stuck }}
        agentName={name}
        conversations={[]}
        onBack={() => moved.push(null)}
        onOpenConversation={() => undefined}
      />
    );
  }
  const watched = () => ({ open: vitest.fn(), close: vitest.fn(), showList: vitest.fn(), forceClose: vitest.fn() });

  // The dock's own close waits for the save and may hold the panel: a page left is simply left.
  it("opens nothing in the dock and closes nothing in it, mounted or taken away with words unsaved", async () => {
    const watch = watched();
    const view = render(<Alone id={NOTE} watch={watch} />);
    await landed();
    typeInto("ab");

    view.unmount();
    await landed();

    for (const move of Object.values(watch)) expect(move).not.toHaveBeenCalled();
    expect(backend.canvas.content(NOTE)).toBe("ab");
  });

  it("goes back when the person closes a canvas whose save is stuck anyway", async () => {
    backend.canvas.refuseNext("PUT", 422);
    render(<Alone id={NOTE} stuck watch={watched()} />);
    await landed();
    typeInto("ab");
    fireEvent.keyDown(editor() as HTMLTextAreaElement, { key: "s", ctrlKey: true });
    await landed();

    fireEvent.click(screen.getByRole("button", { name: canvas.closeAnyway }));

    expect(moved).toEqual([null]);
  });

  it("shows nothing of the canvas it showed before while the next one is read", async () => {
    const watch = watched();
    const view = render(<Alone id={NOTE} watch={watch} />);
    await landed();
    expect(usedButtons()).toEqual([canvas.conversationFallback("c1")]);

    // Both reads of the next canvas are out: the panel's, and the page's of its conversations.
    backend.canvas.canvases.get(SHOP)?.conversationIds.push("c2");
    const holds = [1, 2].map(() => backend.canvas.holdNext(`GET /artifacts/${SHOP}`, "reply"));
    view.rerender(<Alone id={SHOP} watch={watch} />);
    await landed();

    expect(used()).toBeNull();
    expect(editor()).toBeNull();
    await act(async () => {
      await Promise.all(holds.map((release) => release()));
    });
    await landed();
    expect(editor()?.value).toBe("b");
    expect(usedButtons()).toEqual([canvas.conversationFallback("c2")]);
  });
});
