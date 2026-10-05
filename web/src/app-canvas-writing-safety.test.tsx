import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ToolCall } from "./api/types";
import { vi } from "./i18n/vi";
import { DRAFT_DELAY_MS } from "./lib/canvas-runner";
import { focusWrites, layout, openChat, startApp, typeInCanvas } from "./test/canvas-app";
import { landed, stopServer, wait } from "./test/canvas-hook";
import { editor } from "./test/canvas-panel";
import {
  answer,
  canvasToggle,
  ended,
  frame,
  panel,
  piece,
  shownFrame,
  startTurn,
  started,
  stream,
  writingCards,
} from "./test/canvas-writing-turn";
import type { FakeBackend } from "./test/fake-backend";

const BOOK = "0123456789ab";
const UNKNOWN = "feedfeedfeed";
const text = vi.canvas.writing;
const REWRITE = { name: "artifact_rewrite" };

/** `text` as it stands inside a JSON string the model is still writing. */
const inner = (value: string) => JSON.stringify(value).slice(1, -1);

let backend: FakeBackend;

beforeEach(() => {
  backend = startApp();
});

afterEach(() => {
  stopServer();
  Reflect.deleteProperty(window, "pwned");
});

const pwned = () => (window as { pwned?: number }).pwned;
const code = () => shownFrame().querySelector("pre.canvas-code");

describe("a canvas the agent is writing again", () => {
  const rewrite: ToolCall = { id: "w1", name: "artifact_rewrite", arguments: { id: BOOK, content: "Bản mới" } };

  async function openBook() {
    backend.canvas.add({ id: BOOK, title: "Sổ tay", agent_id: "master", content: "Bản cũ", conversationIds: ["c1"] });
    await openChat(1440);
    fireEvent.click(canvasToggle());
    await landed();
    fireEvent.click(screen.getByRole("button", { name: /Sổ tay/ }));
    await landed();
  }

  it("comes up over the canvas it rewrites, which waits behind it and shows again once rewritten", async () => {
    await openBook();
    const held = panel();
    expect(held).not.toBeNull();
    const turn = await startTurn(backend, "viết lại sổ tay");

    await stream(turn, piece(`{"id":"${BOOK}","content":"Bản`, REWRITE));

    expect(within(writingCards()[0]).getByText(text.rewriting)).toBeInTheDocument();
    expect(within(writingCards()[0]).getByText("Sổ tay")).toBeInTheDocument();
    expect(frame()).toBeNull();

    await stream(turn, piece(" mới", REWRITE));

    expect(within(shownFrame()).getByRole("heading", { level: 2, name: "Sổ tay" })).toBeInTheDocument();
    expect(shownFrame()).toHaveTextContent("Bản mới");
    expect(panel()).toBe(held);
    expect(panel()).not.toBeVisible();

    backend.canvas.write(BOOK, "Bản mới");
    await stream(turn, piece('"}', REWRITE), answer([rewrite]), started(rewrite));
    await stream(turn, ended(rewrite, `[artifact ${BOOK} v2]\nCanvas "Sổ tay" was rewritten.`));

    expect(frame()).toBeNull();
    expect(panel()).toBe(held);
    expect(panel()).toBeVisible();
  });

  it("stays a card while another canvas is open, or none", async () => {
    backend.canvas.add({ id: BOOK, title: "Sổ tay", agent_id: "master", content: "Bản cũ", conversationIds: ["c1"] });
    await openChat(1440);
    const turn = await startTurn(backend, "viết lại sổ tay");

    await stream(turn, piece(`{"id":"${BOOK}","content":"Bản`, REWRITE));
    await stream(turn, piece(" mới", REWRITE));

    expect(writingCards()).toHaveLength(1);
    expect(frame()).toBeNull();
    expect(layout()).toHaveClass("with-activity");
  });

  it("asks the server nothing about the canvas its draft names", async () => {
    await openChat(1440);
    const turn = await startTurn(backend, "viết lại");
    await stream(turn, piece(`{"id":"${UNKNOWN}","content":"Bản`, REWRITE));

    fireEvent.click(within(writingCards()[0]).getByRole("button", { name: text.showLabel(text.untitled) }));
    await landed();
    await stream(turn, piece(" mới", REWRITE));

    expect(shownFrame()).toHaveTextContent("Bản mới");
    expect(backend.requests.filter((r) => r.path.includes(UNKNOWN))).toEqual([]);
    expect(focusWrites(backend)).toEqual([]);
  });
});

describe("what this device remembers while the agent writes a canvas again", () => {
  /** Everything the browser was given to keep, keys and values together. */
  const remembered = () => {
    const kept: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i) ?? "";
      kept.push(key, localStorage.getItem(key) ?? "");
    }
    return kept.join("\n");
  };

  it("keeps the person's typing for that canvas, and nothing of what the agent writes", async () => {
    backend.canvas.add({ id: BOOK, title: "Sổ tay", content: "Bản cũ", conversationIds: ["c1"] });
    await openChat(1440);
    fireEvent.click(canvasToggle());
    await landed();
    fireEvent.click(screen.getByRole("button", { name: /Sổ tay/ }));
    await landed();
    const turn = await startTurn(backend, "viết lại sổ tay");
    act(() => editor()?.focus());
    typeInCanvas("chữ của người");
    wait(DRAFT_DELAY_MS);
    expect(localStorage.getItem(`canvas-draft:${BOOK}`)).toContain("chữ của người");

    backend.canvas.refuseNext("PUT", 500);
    await stream(turn, piece(`{"id":"${BOOK}","content":"Nháp của`, REWRITE));
    const show = within(writingCards()[0]).getByRole("button", { name: text.showLabel("Sổ tay") });
    act(() => show.focus());
    fireEvent.click(show);
    await landed();
    await stream(turn, piece(" agent", REWRITE));

    expect(shownFrame()).toHaveTextContent("Nháp của agent");
    expect(remembered()).not.toContain("Nháp của");
    expect(localStorage.getItem(`canvas-draft:${BOOK}`)).toContain("chữ của người");
    expect(backend.canvas.content(BOOK)).toBe("Bản cũ");
    expect(backend.requests.filter((r) => JSON.stringify(r.body ?? null).includes("Nháp của"))).toEqual([]);
  });
});

describe("a draft that turns out not to be a canvas", () => {
  it("is taken down, and nothing of the call's arguments stays in the dock", async () => {
    const other: ToolCall = {
      id: "w1",
      name: "workspace_write",
      arguments: { path: "notes.md", content: "mật khẩu là 1234" },
    };
    await openChat(1440);
    const turn = await startTurn(backend, "ghi vào tệp");
    await stream(turn, piece('{"path":"notes.md","content":"mật khẩu'));
    await stream(turn, piece(" là 1234"));
    expect(shownFrame()).toHaveTextContent("mật khẩu là 1234");

    await stream(turn, answer([other]), started(other));

    expect(frame()).toBeNull();
    expect(writingCards()).toEqual([]);
    expect(document.querySelector(".canvas-dock")?.textContent).not.toContain("mật khẩu");
    expect(layout()).toHaveClass("with-activity");
    expect(canvasToggle()).toHaveAttribute("aria-expanded", "false");
  });
});

describe("what a canvas being written can do to the page", () => {
  const SCRIPT = "<script>window.pwned = 1</script>";
  const MARKUP = '<b onclick="window.pwned = 2">đậm</b><img src="x" onerror="window.pwned = 3">';

  it("shows a page as its source and runs none of it", async () => {
    await openChat(1440);
    const turn = await startTurn(backend, "viết trang web");

    await stream(turn, piece(`{"title":"Trang","kind":"html","content":"${inner(SCRIPT)}`));
    await stream(turn, piece(inner(MARKUP)));

    expect(code()?.textContent).toBe(SCRIPT + MARKUP);
    expect(within(shownFrame()).getByText(text.source)).toBeInTheDocument();
    expect(shownFrame().querySelector("iframe, script, b, img")).toBeNull();
    expect(document.querySelector("iframe")).toBeNull();
    expect(pwned()).toBeUndefined();
  });

  it("draws markdown as a stored canvas does, with the markup in it left as text", async () => {
    await openChat(1440);
    const turn = await startTurn(backend, "viết ghi chú");

    await stream(turn, piece(`{"title":"Ghi","kind":"markdown","content":"${inner(`${SCRIPT}\n\n`)}`));
    await stream(turn, piece(inner(`**quan trọng** ${MARKUP}`)));

    expect(within(shownFrame()).getByText("quan trọng").tagName).toBe("STRONG");
    expect(shownFrame().querySelector("iframe, script, img, [onclick]")).toBeNull();
    expect(pwned()).toBeUndefined();
  });

  it("draws a kind it does not know as text", async () => {
    await openChat(1440);
    const turn = await startTurn(backend, "viết gì đó");

    await stream(turn, piece(`{"title":"Lạ","kind":"constructor","content":"${inner(SCRIPT)}`));
    await stream(turn, piece(inner(MARKUP)));

    expect(code()?.textContent).toBe(SCRIPT + MARKUP);
    expect(shownFrame().querySelector(".badge")).toBeNull();
    expect(shownFrame().querySelector("iframe, script, b, img")).toBeNull();
    expect(pwned()).toBeUndefined();
  });

  it("holds the title to what a stored canvas may be called", async () => {
    const BIDI = String.fromCharCode(0x202e);
    await openChat(1440);
    const turn = await startTurn(backend, "viết");

    await stream(turn, piece(`{"title":"${inner(`an${BIDI}toàn`)}","content":"A`));
    await stream(turn, piece("B"));

    expect(shownFrame().querySelector("h2")?.textContent).toBe("antoàn");
    expect(writingCards()[0].querySelector(".canvas-card-title")?.textContent).toBe("antoàn");
  });
});
