import { act, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentEvent } from "./api/types";
import { vi } from "./i18n/vi";
import { errorReport } from "./lib/error-report";
import {
  bodies,
  conversation,
  focusWrites,
  layout,
  openChat,
  openNote,
  posts,
  say,
  startApp,
  traffic,
} from "./test/canvas-app";
import { askButton, bar, excerpt, openBox, pressSend, questionBox, typeQuestion } from "./test/canvas-ask";
import { landed, stopServer } from "./test/canvas-hook";
import { editor, typeInto } from "./test/canvas-panel";
import { pick, pickIn } from "./test/canvas-pick";
import { type FakeBackend, FakeEventSource, fakeApproval, fakeRun } from "./test/fake-backend";
import { SAMPLES } from "./test/fake-canvas-kinds";

const TEXT = "Đoạn một\n\nĐoạn hai\n\nĐoạn ba\n";
const PASSAGE = "Đoạn hai";
const QUESTION = "vì sao đoạn này sai?";
const NOTE = `[Canvas "Ghi chú" v2, dòng 3]\n> ${PASSAGE}`;
const DONE: AgentEvent = { type: "done", spent_usd: 0, unknown_cost_calls: 0 };

let backend: FakeBackend;

beforeEach(() => {
  backend = startApp();
});

afterEach(stopServer);

/** The canvas as the person last wrote it, which opens to be edited. */
const mine = () => backend.canvas.write("a1", TEXT, { author: "user" });
/** The canvas as an agent wrote it, which opens to be read. */
const theirs = () => backend.canvas.write("a1", TEXT);

/** The message a question about `PASSAGE` makes, the canvas being at its second version. */
const asking = (text = QUESTION) => ({
  text,
  canvas: { artifact_id: "a1", selection: { version: 2, text: PASSAGE, line_start: 3, line_end: 3 } },
});

const settle = async () => {
  for (let i = 0; i < 4; i++) await landed();
};
const main = () => document.querySelector("main") as HTMLElement;
const overlay = () => screen.queryByRole("region", { name: vi.canvas.button });
const pickEditing = () => pickIn(editor() as HTMLTextAreaElement, PASSAGE);
const pickReading = () => pick(document.querySelector(".canvas-view") as HTMLElement, PASSAGE);

/** The person writes the question in the box, presses Gửi, and the send is let run. */
async function ask(question = QUESTION) {
  openBox();
  typeQuestion(question);
  pressSend();
  await settle();
}

/**
 * From now on the server takes a message at once but its reply reaches the tab only when the
 * returned function is called, whatever became of the conversation it was sent to meanwhile.
 */
function holdMessageReplies(): () => void {
  let open = () => {};
  const shut = new Promise<void>((resolve) => (open = resolve));
  const real = backend.fetch;
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await real(input, init);
    if (String(input).endsWith("/messages")) await shut;
    return response;
  });
  return open;
}

describe("asking the agent about a passage of the canvas beside the chat", () => {
  it("sends the passage with the question as one message, and saves and writes nothing besides", async () => {
    mine();
    await openChat(1440);
    await openNote();
    pickEditing();

    await ask();

    expect(bodies(backend)).toEqual([asking()]);
    expect(traffic(backend)).not.toContain("PUT /artifacts/a1");
    expect(focusWrites(backend)).toEqual([]);
    expect(bar()).toBeNull();
  });

  it("does the same for a canvas that is being read", async () => {
    theirs();
    await openChat(1440);
    await openNote();
    pickReading();

    await ask();

    expect(bodies(backend)).toEqual([asking()]);
    expect(traffic(backend)).not.toContain("PUT /artifacts/a1");
    expect(bar()).toBeNull();
  });

  it("saves what was typed first, and asks about the passage as the saved version holds it", async () => {
    mine();
    await openChat(1440);
    await openNote();
    typeInto(TEXT.replace(PASSAGE, "Đoạn hai sửa"));
    pickIn(editor() as HTMLTextAreaElement, "Đoạn hai sửa");

    await ask();

    expect(traffic(backend).indexOf("PUT /artifacts/a1")).toBeGreaterThan(-1);
    expect(traffic(backend).indexOf("PUT /artifacts/a1")).toBeLessThan(
      traffic(backend).indexOf("POST /conversations/c1/messages"),
    );
    expect(bodies(backend)).toEqual([
      { text: QUESTION, canvas: { artifact_id: "a1", selection: { version: 3, text: "Đoạn hai sửa", line_start: 3, line_end: 3 } } },
    ]);
  });

  it("gives the person's message the chip of the note the server kept with the question", async () => {
    mine();
    backend.nextTurn = [{ type: "user_context", context: NOTE }, DONE];
    await openChat(1440);
    await openNote();
    pickEditing();

    await ask();

    const message = screen.getByTestId("message-user");
    const note = screen.getByTestId("canvas-note");
    expect(message).toHaveTextContent(QUESTION);
    expect(message.nextElementSibling).toBe(note);
    fireEvent.click(within(note).getByRole("button", { name: vi.canvas.noteChip }));
    expect(screen.getByTestId("canvas-note-body")).toHaveTextContent(PASSAGE);
  });

  it("closes the box but keeps the canvas beside the chat while the turn it began is still running", async () => {
    mine();
    backend.nextTurn = [{ type: "user_context", context: NOTE }];
    const turn = backend.holdTurn("c1");
    await openChat(1440);
    await openNote();
    pickEditing();

    await ask();

    expect(questionBox()).toBeNull();
    expect(bar()).toBeNull();
    expect(screen.getByRole("button", { name: vi.stop })).toBeInTheDocument();
    expect(layout()).toHaveClass("with-canvas");
    expect(screen.getByRole("heading", { level: 2, name: "Ghi chú" })).toBeInTheDocument();
    await act(async () => turn.release());
    await settle();
  });

  it("closes the box when the server queued the question behind a turn this tab could not see", async () => {
    mine();
    await openChat(1440);
    await openNote();
    pickEditing();
    const elsewhere = backend.holdTurn("c1");
    await backend.fetch("/api/conversations/c1/messages", {
      method: "POST",
      body: JSON.stringify({ text: "việc của tab kia" }),
    });

    await ask();

    expect(screen.getByRole("list", { name: vi.queuedLabel })).toHaveTextContent(QUESTION);
    expect(questionBox()).toBeNull();
    expect(bar()).toBeNull();
    elsewhere.release();
  });
});

describe("a question that does not reach the agent", () => {
  it.each([
    [409, "conversation is awaiting approval", vi.busyConflict],
    [422, "the selection does not fit the canvas at version 2", vi.sendFailed.selection],
    [429, "the queue is full", vi.sendFailed.tooFast],
  ])("is turned down with %i: the box keeps the question and says why, and the next try goes through", async (status, detail, why) => {
    mine();
    await openChat(1440);
    await openNote();
    pickEditing();
    backend.refuseMessage = { status, detail };

    await ask();

    expect(within(bar() as HTMLElement).getByRole("alert")).toHaveTextContent(why);
    expect(within(bar() as HTMLElement).queryByText(detail)).toBeNull();
    expect(questionBox()).toHaveValue(QUESTION);
    expect(excerpt()).toBe(PASSAGE);
    expect(screen.queryAllByTestId("message-user")).toEqual([]);

    backend.refuseMessage = null;
    pressSend();
    await settle();

    expect(questionBox()).toBeNull();
    expect(bodies(backend)).toEqual([asking(), asking()]);
    expect(screen.getByTestId("message-user")).toHaveTextContent(QUESTION);
  });

  it("is lost on the way: the box keeps the question and says the server cannot be reached", async () => {
    mine();
    await openChat(1440);
    await openNote();
    pickEditing();
    const real = backend.fetch;
    vitest.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) =>
      String(input).endsWith("/messages") ? Promise.reject(new TypeError("Failed to fetch")) : real(input, init),
    );

    await ask();

    expect(within(bar() as HTMLElement).getByRole("alert")).toHaveTextContent(vi.requestErrors.network);
    expect(questionBox()).toHaveValue(QUESTION);

    vitest.stubGlobal("fetch", real);
    pressSend();
    await settle();

    expect(questionBox()).toBeNull();
    expect(screen.getByTestId("message-user")).toHaveTextContent(QUESTION);
  });

  it("is never sent when the person goes to another conversation before the canvas is saved", async () => {
    mine();
    await openChat(1440);
    await openNote();
    typeInto(TEXT.replace(PASSAGE, "Đoạn hai sửa"));
    pickIn(editor() as HTMLTextAreaElement, "Đoạn hai sửa");
    const release = backend.canvas.holdNext("PUT");
    openBox();
    typeQuestion(QUESTION);
    pressSend();
    await settle();
    expect(posts(backend)).toEqual([]);

    fireEvent.click(conversation("Hai"));
    await settle();
    await act(() => release());
    await settle();

    expect(posts(backend, "c1")).toEqual([]);
    expect(posts(backend, "c2")).toEqual([]);
  });
});

describe("asking from a canvas that covers the chat", () => {
  it("puts the canvas away once the question went through, so that the answer shows", async () => {
    mine();
    backend.nextTurn = [{ type: "user_context", context: NOTE }];
    const turn = backend.holdTurn("c1");
    await openChat(390);
    await openNote();
    expect(overlay()).toBeInTheDocument();
    pickEditing();

    await ask();

    expect(overlay()).toBeNull();
    expect(main()).not.toHaveAttribute("inert");
    expect(screen.getByRole("button", { name: vi.stop })).toBeInTheDocument();
    expect(screen.getByTestId("message-user")).toHaveTextContent(QUESTION);
    await act(async () => turn.release());
    await settle();
  });

  it("keeps the canvas and the question when the server turned the question down", async () => {
    mine();
    await openChat(390);
    await openNote();
    pickEditing();
    backend.refuseMessage = { status: 429, detail: "the queue is full" };

    await ask();

    expect(overlay()).toBeInTheDocument();
    expect(questionBox()).toHaveValue(QUESTION);
    expect(main()).toHaveAttribute("inert");
  });

  it("closes only the box on Escape in it, and leaves the canvas open", async () => {
    mine();
    await openChat(390);
    await openNote();
    pickEditing();
    openBox();

    fireEvent.keyDown(questionBox() as HTMLElement, { key: "Escape" });

    expect(questionBox()).toBeNull();
    expect(askButton()).toBeInTheDocument();
    expect(overlay()).toBeInTheDocument();
  });

  it("leaves alone what the person opened in another conversation while the question was on its way", async () => {
    mine();
    await openChat(1000);
    await openNote();
    pickEditing();
    const open = holdMessageReplies();
    openBox();
    typeQuestion(QUESTION);
    pressSend();
    await settle();

    fireEvent.click(conversation("Hai"));
    await settle();
    fireEvent.click(screen.getByRole("button", { name: vi.canvas.buttonLabel(0) }));
    await settle();
    expect(overlay()).toBeInTheDocument();
    await act(async () => open());
    await settle();

    expect(overlay()).toBeInTheDocument();
  });
});

describe("asking while the chat cannot take a question", () => {
  const stream = () => FakeEventSource.instances.at(-1) as FakeEventSource;
  const reason = (words: string) => screen.queryByText(words);
  const c1 = () => backend.conversations.get("c1") as NonNullable<ReturnType<typeof backend.conversations.get>>;
  /** Another channel has a turn going in the first conversation, which this tab does not stream. */
  const runElsewhere = () =>
    act(() => {
      stream().open();
      stream().emit({
        type: "snapshot",
        runs: [fakeRun({ id: "r9", conversation_id: "c1", source: "telegram", status: "running", finished_at: null })],
      });
    });
  const awaitingDecision = () =>
    Object.assign(c1(), {
      status: "awaiting_approval",
      pending_approval: fakeApproval({ id: "ap1", conversation_id: "c1", status: "pending", resolved_at: null }),
    });
  const overBudget = () => Object.assign(c1(), { spent_usd: 1, over_budget: true });

  it("is off while a turn of this tab is running, and on again once it is over", async () => {
    mine();
    backend.nextTurn = [
      { type: "assistant_message", message_id: "m1", content: "Đang xem", tool_calls: [], provider: null, model: null, cost_usd: null },
    ];
    const turn = backend.holdTurn("c1");
    await openChat(1440);
    await openNote();
    await say("xem giúp tôi");
    pickEditing();

    expect(askButton()).toBeDisabled();
    expect(reason(vi.canvas.ask.busy)).toBeInTheDocument();

    await act(async () => turn.release());
    await settle();

    expect(askButton()).toBeEnabled();
    expect(reason(vi.canvas.ask.busy)).toBeNull();
  });

  it("is off while another channel has a turn going in the conversation", async () => {
    mine();
    await openChat(1440);
    await openNote();
    runElsewhere();
    pickEditing();

    expect(askButton()).toBeDisabled();
    expect(reason(vi.canvas.ask.busy)).toBeInTheDocument();
  });

  it("is off while the conversation waits for a decision on a tool", async () => {
    mine();
    awaitingDecision();
    await openChat(1440);
    await openNote();
    pickEditing();

    expect(askButton()).toBeDisabled();
    expect(reason(vi.canvas.ask.pending)).toBeInTheDocument();
  });

  it("is off once the conversation has spent its budget", async () => {
    mine();
    overBudget();
    await openChat(1440);
    await openNote();
    pickEditing();

    expect(askButton()).toBeDisabled();
    expect(reason(vi.canvas.ask.budget)).toBeInTheDocument();
  });

  it("gives one reason at a time: a decision to take before the budget, a turn running before both", async () => {
    mine();
    awaitingDecision();
    overBudget();
    await openChat(1440);
    await openNote();
    pickEditing();
    expect(reason(vi.canvas.ask.pending)).toBeInTheDocument();
    expect(reason(vi.canvas.ask.budget)).toBeNull();

    runElsewhere();

    expect(reason(vi.canvas.ask.busy)).toBeInTheDocument();
    expect(reason(vi.canvas.ask.pending)).toBeNull();
    expect(reason(vi.canvas.ask.budget)).toBeNull();
  });
});

describe("sending the errors a page reported from the canvas beside the chat", () => {
  const FAILURE = { message: "Uncaught ReferenceError: dem is not defined", source: "", line: 12, column: 3 };

  /** The page in the frame reports `FAILURE`, as the browser delivers it from a sandboxed frame. */
  function pageReports() {
    const frame = document.querySelector("iframe.canvas-frame") as HTMLIFrameElement;
    act(() => {
      window.dispatchEvent(
        Object.assign(new Event("message"), {
          source: frame.contentWindow,
          origin: "null",
          data: { type: "canvas-error", ...FAILURE },
        }),
      );
    });
  }

  it("sends them as one message that names the canvas and no passage, only when asked, and writes no focus", async () => {
    backend.canvas.add({ ...SAMPLES.html, agent_id: "ming", conversationIds: ["c1"] });
    await openChat(1440);
    fireEvent.click(screen.getByRole("button", { name: vi.canvas.buttonLabel(2) }));
    await landed();
    fireEvent.click(screen.getByRole("button", { name: /Trang hẹn giờ/ }));
    await landed();

    pageReports();
    await settle();
    expect(posts(backend)).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: vi.canvas.pageErrors.send }));
    await settle();

    expect(bodies(backend)).toEqual([
      { text: errorReport("Trang hẹn giờ", 1, [FAILURE]), canvas: { artifact_id: "a2", selection: null } },
    ]);
    expect(focusWrites(backend)).toEqual([]);
    expect(traffic(backend)).not.toContain("PUT /artifacts/a2");
    expect(screen.getByText(vi.canvas.pageErrors.sent(1))).toBeInTheDocument();
  });
});
