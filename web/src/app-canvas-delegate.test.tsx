import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { AgentEvent } from "./api/types";
import { vi } from "./i18n/vi";
import { bodies, box, focusWrites, layout, openChat, openNote, say, startApp } from "./test/canvas-app";
import { landed, stopServer } from "./test/canvas-hook";
import { editor } from "./test/canvas-panel";
import { type FakeBackend, storedMessage } from "./test/fake-backend";

const PLAN = "00ff00ff00ff";
const SHOP = "ba9876543210";
const LOST = "0000000000ff";
const REPORT = "Báo cáo tuần";
const ANNEX = "Phụ lục";
const TASK = { agent: "coach", task: "viết báo cáo tuần" };
const { card } = vi.canvas;

const line = (id: string, version: number, title: string) => `[artifact ${id} v${version}] ${title}`;

/** What the handed-off task returns, as the server writes it: the canvases it wrote above a blank line. */
const result = (canvases: string[], reply = "Đã viết báo cáo.") =>
  ["conversation=child1 status=done spent=$0.0100 steps=3", "outcome=done", ...canvases, "", reply].join("\n");

/** The task wrote the report, then its annex, which it named before the name was changed. */
const WROTE = result([line(PLAN, 2, REPORT), line(SHOP, 1, "Phụ lục nháp")]);
/** The call gave up waiting on a task still going, which had written the report by then. */
const TIMED_OUT = ["conversation=child1 status=running spent=$0.0100 steps=3", "outcome=failed reason=timeout", line(PLAN, 1, REPORT), "", ""].join("\n");

let backend: FakeBackend;

beforeEach(() => {
  backend = startApp();
});

afterEach(stopServer);

/** The canvases the other agent wrote. They are its own: the conversation asking is not given them. */
function written() {
  backend.canvas.add({ id: PLAN, title: REPORT, agent_id: "coach", content: "Tuần này\n\nBa việc xong", version: 2 });
  backend.canvas.add({ id: SHOP, title: ANNEX, agent_id: "coach", content: "Số liệu" });
}

/** A turn in which the agent hands the task off and says how it went, as the server streams it. */
const handOffTurn = (output: string, ok = true): AgentEvent[] => [
  {
    type: "assistant_message",
    message_id: "a1",
    content: "",
    tool_calls: [{ id: "d1", name: "delegate", arguments: TASK }],
    provider: null,
    model: null,
    cost_usd: null,
  },
  { type: "tool_call", tool_call_id: "d1", name: "delegate", arguments: TASK },
  { type: "tool_result", tool_call_id: "d1", name: "delegate", ok, output },
  {
    type: "assistant_message",
    message_id: "a2",
    content: "Việc đã xong.",
    tool_calls: [],
    provider: null,
    model: null,
    cost_usd: null,
  },
  { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
];

/** The first conversation already holds the turn above, saved in an earlier visit. */
function saveEarlierTurn(output: string) {
  const call = { id: "old1", name: "delegate", arguments: TASK };
  backend.conversations
    .get("c1")
    ?.messages.push(
      storedMessage("user", "giao việc viết báo cáo"),
      storedMessage("assistant", "", { tool_calls: [call] }),
      storedMessage("tool", output, { tool_call_id: "old1", name: "delegate" }),
      storedMessage("assistant", "Việc đã xong."),
    );
}

/** The person hands the task off, and what the card then asks of the server is let land. */
async function handOff(output: string, ok = true) {
  backend.nextTurn = handOffTurn(output, ok);
  await say("giao việc viết báo cáo");
  await landed();
  await landed();
}

const panelTitle = (name: string) => screen.queryByRole("heading", { level: 2, name });
const main = () => document.querySelector("main") as HTMLElement;
const delegateCard = () => screen.getByTestId("delegate-card");
const chips = () => within(delegateCard()).queryAllByTestId("delegate-canvas");
const openButton = (title: string) => within(delegateCard()).getByRole("button", { name: card.openLabel(title) });
/** The reads of one canvas, which a card makes to learn whether it is still there. */
const reads = (id: string) => backend.requests.filter((r) => r.method === "GET" && r.path === `/artifacts/${id}`);

describe("the canvases a task handed off in a turn this tab is showing wrote", () => {
  it("are named on its card, and the first opens beside the thread with the keyboard left in the box and nothing written", async () => {
    written();
    await openChat(1440);
    act(() => box().focus());

    await handOff(WROTE);

    expect(chips().map((chip) => chip.textContent)).toEqual([`${REPORT}v2${card.open}`, `${ANNEX}v1${card.open}`]);
    expect(layout()).toHaveClass("with-canvas");
    expect(panelTitle(REPORT)).toBeInTheDocument();
    expect(panelTitle(ANNEX)).toBeNull();
    expect(box()).toHaveFocus();
    expect(focusWrites(backend)).toEqual([]);
  });

  it("go by the name the server has for them, asked once of each the conversation's own list does not hold", async () => {
    written();
    await openChat(1440);

    await handOff(WROTE);

    expect(within(delegateCard()).queryByText("Phụ lục nháp")).toBeNull();
    expect(openButton(ANNEX)).toBeInTheDocument();
    expect(reads(SHOP)).toHaveLength(1);
  });

  it("goes with the next message the person sends, the one that opened by itself, as the canvas they have open", async () => {
    written();
    await openChat(1440);
    await handOff(WROTE);

    await say("rút gọn giúp tôi");

    expect(bodies(backend)).toEqual([
      { text: "giao việc viết báo cáo" },
      { text: "rút gọn giúp tôi", canvas: { artifact_id: PLAN, selection: null } },
    ]);
  });

  it("open from their card when asked, in place of the one that opened by itself, and write nothing", async () => {
    written();
    await openChat(1440);
    await handOff(WROTE);

    fireEvent.click(openButton(ANNEX));
    await landed();

    expect(panelTitle(ANNEX)).toBeInTheDocument();
    expect(panelTitle(REPORT)).toBeNull();
    expect(focusWrites(backend)).toEqual([]);

    await say("rút gọn giúp tôi");

    expect(bodies(backend).at(-1)).toEqual({ text: "rút gọn giúp tôi", canvas: { artifact_id: SHOP, selection: null } });
  });

  it("take the place of a canvas the person had open and was not writing in", async () => {
    written();
    await openChat(1440);
    await openNote();
    expect(panelTitle("Ghi chú")).toBeInTheDocument();

    await handOff(WROTE);

    expect(panelTitle(REPORT)).toBeInTheDocument();
    expect(panelTitle("Ghi chú")).toBeNull();
  });

  it("do not take the panel from a canvas the person has the keyboard in", async () => {
    written();
    await openChat(1440);
    await openNote();
    act(() => editor()?.focus());

    await handOff(WROTE);

    expect(panelTitle("Ghi chú")).toBeInTheDocument();
    expect(panelTitle(REPORT)).toBeNull();
    expect(editor()).toHaveFocus();
    expect(chips()).toHaveLength(2);
  });

  it("stop being offered once deleted, while the other still is", async () => {
    written();
    await openChat(1440);
    await handOff(WROTE);

    act(() => backend.canvas.remove(SHOP));
    await landed();

    const [kept, gone] = chips();
    expect(within(gone).getByText(vi.canvas.gone)).toBeInTheDocument();
    expect(within(gone).queryByRole("button")).toBeNull();
    expect(within(kept).getByRole("button", { name: card.openLabel(REPORT) })).toBeInTheDocument();
  });
});

describe("a task handed off in a turn this tab is showing that leaves no canvas to open", () => {
  it("wrote none: its card names none, nothing opens, and the server is asked about none", async () => {
    written();
    await openChat(1440);

    await handOff(result([]));

    expect(delegateCard()).toBeInTheDocument();
    expect(chips()).toEqual([]);
    expect(within(delegateCard()).queryByRole("list")).toBeNull();
    expect(layout()).not.toHaveClass("with-canvas");
    expect(reads(PLAN)).toEqual([]);
  });

  it("only spoke of one, in a reply that opens with a line like the server's: its card names none and nothing opens", async () => {
    written();
    await openChat(1440);

    await handOff(result([], `${line(PLAN, 2, REPORT)}\n\nXem canvas trên.`));

    expect(chips()).toEqual([]);
    expect(layout()).not.toHaveClass("with-canvas");
    expect(reads(PLAN)).toEqual([]);
  });

  it("ran out of time: its card names the canvas written by then, and nothing opens by itself", async () => {
    written();
    await openChat(1440);

    await handOff(TIMED_OUT, false);

    expect(within(delegateCard()).getByTestId("delegate-reason")).toHaveTextContent(vi.delegateTimeout);
    expect(chips().map((chip) => chip.textContent)).toEqual([`${REPORT}v1${card.open}`]);
    expect(layout()).not.toHaveClass("with-canvas");
    expect(panelTitle(REPORT)).toBeNull();

    fireEvent.click(openButton(REPORT));
    await landed();

    expect(layout()).toHaveClass("with-canvas");
    expect(panelTitle(REPORT)).toBeInTheDocument();
  });
});

describe("the canvases a handed-off task wrote, on a screen too narrow to hold one beside the thread", () => {
  it("are named on its card with a way to open each, and none opens by itself", async () => {
    written();
    await openChat(1000);

    await handOff(WROTE);

    expect(main()).not.toHaveAttribute("inert");
    expect(screen.queryByRole("region", { name: vi.canvas.button })).toBeNull();
    expect(chips()).toHaveLength(2);

    fireEvent.click(openButton(ANNEX));
    await landed();

    expect(screen.getByRole("region", { name: vi.canvas.button })).toBeInTheDocument();
    expect(panelTitle(ANNEX)).toBeInTheDocument();
    expect(main()).toHaveAttribute("inert");
  });
});

describe("the canvases a task handed off in an earlier turn wrote", () => {
  it("are named on its card in the saved thread, and open only when asked, taking the keyboard into the dock", async () => {
    written();
    saveEarlierTurn(WROTE);
    await openChat(1440);
    await landed();

    expect(layout()).not.toHaveClass("with-canvas");
    expect(panelTitle(REPORT)).toBeNull();
    expect(chips().map((chip) => chip.textContent)).toEqual([`${REPORT}v2${card.open}`, `${ANNEX}v1${card.open}`]);

    act(() => openButton(REPORT).focus());
    fireEvent.click(openButton(REPORT));
    await landed();

    expect(layout()).toHaveClass("with-canvas");
    expect(panelTitle(REPORT)).toBeInTheDocument();
    expect(document.querySelector(".dock-canvas")).toContainElement(document.activeElement as HTMLElement);
  });

  it("say so, with nothing to open, when the server no longer has one of them", async () => {
    written();
    saveEarlierTurn(result([line(LOST, 3, "Bản đã xoá"), line(PLAN, 2, REPORT)]));
    await openChat(1440);
    await landed();

    const [gone, kept] = chips();
    expect(gone).toHaveTextContent("Bản đã xoá");
    expect(within(gone).getByText(vi.canvas.gone)).toBeInTheDocument();
    expect(within(gone).queryByRole("button")).toBeNull();
    expect(within(kept).getByRole("button", { name: card.openLabel(REPORT) })).toBeInTheDocument();
    expect(layout()).not.toHaveClass("with-canvas");
  });
});
