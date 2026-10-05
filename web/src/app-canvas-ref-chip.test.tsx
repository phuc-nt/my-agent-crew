import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { vi } from "./i18n/vi";
import { layout, openChat, startApp } from "./test/canvas-app";
import { landed, stopServer } from "./test/canvas-hook";
import { frame, panel, piece, shownFrame, startOver, startTurn, stream, writingCards } from "./test/canvas-writing-turn";
import { type FakeBackend, storedMessage } from "./test/fake-backend";

const BOOK = "0123456789ab";
const REPORT = "00ff00ff00ff";
const LOST = "0000000000ff";
const { card } = vi.canvas;

/** The arguments of a canvas the agent is making, as the model writes them, in two pieces. */
const HEAD = '{"title":"Kế hoạch tuần","kind":"markdown","content":"Việc';
const MORE = " một\\n\\nViệc";
const LAST = ' hai"}';

let backend: FakeBackend;

beforeEach(() => {
  backend = startApp();
});

afterEach(stopServer);

/** The conversation holds a reply, saved in an earlier visit, that sent each of these canvases as a file. */
function sentAsFiles(...ids: string[]) {
  const lines = ids.map((id) => `FILE: artifact:${id}`);
  backend.conversations
    .get("c1")
    ?.messages.push(storedMessage("user", "gửi sổ tay"), storedMessage("assistant", ["Sổ tay đây:", ...lines].join("\n")));
}

const chips = () => screen.queryAllByTestId("canvas-ref");
const openButton = (title: string) => screen.getByRole("button", { name: card.openLabel(title) });
const shownTitle = (name: string) => {
  const stored = panel();
  return stored && within(stored).queryByRole("heading", { level: 2, name });
};
/** The reads of one canvas, which a chip makes to learn whether it is still there. */
const reads = (id: string) => backend.requests.filter((r) => r.method === "GET" && r.path === `/artifacts/${id}`);

describe("a line of a saved reply that sends a canvas", () => {
  it("is a chip named after the canvas, which opens it beside the thread", async () => {
    backend.canvas.add({ id: BOOK, title: "Sổ tay", agent_id: "master", content: "Bản cũ", conversationIds: ["c1"] });
    sentAsFiles(BOOK);
    await openChat(1440);

    expect(chips().map((chip) => chip.textContent)).toEqual([`Sổ tay${card.open}`]);
    expect(screen.queryByTestId("message-file")).toBeNull();
    expect(panel()).toBeNull();

    fireEvent.click(openButton("Sổ tay"));
    await landed();

    expect(layout()).toHaveClass("with-canvas");
    expect(shownTitle("Sổ tay")).toBeVisible();
  });

  it("puts away the canvas the agent is writing when pressed, and shows the one it names", async () => {
    backend.canvas.add({ id: BOOK, title: "Sổ tay", agent_id: "master", content: "Bản cũ", conversationIds: ["c1"] });
    sentAsFiles(BOOK);
    await openChat(1440);
    const turn = await startTurn(backend);
    await stream(turn, piece(HEAD));
    await stream(turn, piece(MORE));
    expect(shownFrame()).toHaveTextContent("Việc một");
    expect(panel()).toBeNull();

    fireEvent.click(openButton("Sổ tay"));
    await landed();

    expect(frame()).toBeNull();
    expect(shownTitle("Sổ tay")).toBeVisible();
    expect(writingCards()).toHaveLength(1);
  });

  it("keeps what the agent writes away for the rest of the turn once pressed, with its card left to bring it back", async () => {
    // Opening another canvas by hand while the agent's shows is putting the agent's away by hand.
    backend.canvas.add({ id: BOOK, title: "Sổ tay", agent_id: "master", content: "Bản cũ", conversationIds: ["c1"] });
    sentAsFiles(BOOK);
    await openChat(1440);
    const turn = await startTurn(backend);
    await stream(turn, piece(HEAD));
    await stream(turn, piece(MORE));
    fireEvent.click(openButton("Sổ tay"));
    await landed();

    await stream(turn, piece(LAST));
    expect(frame()).toBeNull();

    // The model starts its answer over and writes another canvas, far enough for one to come up by itself.
    await stream(turn, ...startOver(1));
    await stream(turn, piece('{"title":"Bản mới","content":"A', { attempt: 1 }));
    await stream(turn, piece("B", { attempt: 1 }));

    expect(frame()).toBeNull();
    expect(shownTitle("Sổ tay")).toBeVisible();
    expect(writingCards()).toHaveLength(1);

    fireEvent.click(within(writingCards()[0]).getByRole("button", { name: vi.canvas.writing.showLabel("Bản mới") }));
    await landed();

    expect(within(shownFrame()).getByRole("heading", { level: 2, name: "Bản mới" })).toBeInTheDocument();
    expect(shownFrame().querySelector("pre.canvas-code")?.textContent).toBe("AB");
  });

  it("goes by the name the server has for a canvas that is not this conversation's, asked of it once", async () => {
    backend.canvas.add({ id: REPORT, title: "Báo cáo tuần", agent_id: "coach", content: "Tuần này" });
    sentAsFiles(REPORT);
    await openChat(1440);
    await landed();

    expect(chips().map((chip) => chip.textContent)).toEqual([`Báo cáo tuần${card.open}`]);
    expect(reads(REPORT)).toHaveLength(1);
  });

  it("says a canvas the server no longer has was deleted, beside one that is still there", async () => {
    backend.canvas.add({ id: BOOK, title: "Sổ tay", agent_id: "master", content: "Bản cũ", conversationIds: ["c1"] });
    sentAsFiles(LOST, BOOK);
    await openChat(1440);
    await landed();

    expect(chips().map((chip) => chip.textContent)).toEqual([`${card.untitled}${vi.canvas.gone}`, `Sổ tay${card.open}`]);
    expect(within(chips()[0]).queryByRole("button")).toBeNull();
  });

  it("leaves a line whose id is not one canvas's as it was written, and says nothing was deleted", async () => {
    // The canvas is there all along: only the line that meant it is written wrong.
    backend.canvas.add({ id: BOOK, title: "Sổ tay", agent_id: "master", content: "Bản cũ" });
    const lines = ["FILE: artifact:xyz", `FILE: artifact:${BOOK}.md`, `MEDIA: artifact:${BOOK}.`];
    backend.conversations
      .get("c1")
      ?.messages.push(storedMessage("user", "gửi sổ tay"), storedMessage("assistant", ["Sổ tay đây:", ...lines].join("\n")));
    await openChat(1440);
    await landed();

    const reply = screen.getByTestId("message-assistant");
    expect(lines.map((line) => within(reply).getByText(line).tagName)).toEqual(["P", "P", "P"]);
    expect(chips()).toEqual([]);
    expect(reply).not.toHaveTextContent(vi.canvas.gone);
    expect(within(reply).queryByRole("button", { name: card.openLabel(card.untitled) })).toBeNull();
    expect(screen.queryByTestId("message-file")).toBeNull();
    expect(reply.querySelector("img.media")).toBeNull();
    expect(backend.requests.filter((r) => r.path.startsWith("/artifacts/"))).toEqual([]);
  });
});
