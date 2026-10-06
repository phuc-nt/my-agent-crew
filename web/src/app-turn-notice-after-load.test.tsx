import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentEvent, ConversationDetail, RunInfo } from "./api/types";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, fakeRun, storedMessage } from "./test/fake-backend";

// What a turn said of itself, that it ended in an error or went on by another route, is on
// screen and nowhere else. The conversation is read again once the turn is over whenever its
// opening load was overtaken by the message, and always in a tab that only read along: the
// notice must still be there afterwards, or the person is left with no word of what happened.

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "";
});

afterEach(() => vitest.unstubAllGlobals());

function stream(): FakeEventSource {
  const source = FakeEventSource.instances.at(-1);
  if (!source) throw new Error("the app has not subscribed to the activity stream");
  return source;
}

function run(conversationId: string, status: RunInfo["status"], id = "r1"): RunInfo {
  const live = status === "running" || status === "awaiting_approval";
  return fakeRun({ id, conversation_id: conversationId, source: "telegram", status, finished_at: live ? null : "2026-10-06T08:00:05Z" });
}

/** A door the test opens by hand: the fetch behind it answers only then. */
function door() {
  let open = () => {};
  const shut = new Promise<void>((resolve) => (open = resolve));
  return { shut, open };
}

/** Keeps back the answers the test names. Each is taken when its request arrives and handed
 *  over when its door opens, as a slow connection would: a load carries the thread as it was
 *  when it was asked for. A door that is open keeps nothing back. */
function slow(conversationId: string, doors: { load?: { shut: Promise<void> }; turn?: { shut: Promise<void> } }) {
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await backend.fetch(input, init);
    const path = String(input);
    if (path.endsWith("/messages")) await doors.turn?.shut;
    else if (!init?.method && path.endsWith(`/conversations/${conversationId}`)) await doors.load?.shut;
    return response;
  });
}

const userBubble = (text: string) =>
  screen.getAllByTestId("message-user").find((bubble) => within(bubble).queryByText(text) !== null);

const threadLoads = (id: string) =>
  backend.requests.filter((r) => r.method === "GET" && r.path === `/conversations/${id}`).length;

const ERROR: AgentEvent[] = [{ type: "error", message: "all routes failed" }];
const MOVED: AgentEvent[] = [
  { type: "escalated", reason: "error", provider: "fake", model: "echo", error: "every route failed" },
  { type: "assistant_message", message_id: "a1", content: "Đã xong.", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
  { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
];

async function openConversation(title: string) {
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: new RegExp(title) }));
  await screen.findByRole("heading", { level: 1, name: title });
  act(() => {
    stream().open();
    stream().emit({ type: "snapshot", runs: [] });
  });
}

describe("a message sent before the conversation's opening load had landed", () => {
  /** Opens the conversation with its opening load kept back, sends "tin mới", lets the load
   *  land behind the message, then lets the turn say `events` and end. `stores` is what the
   *  server has stored by then, beside the message itself. */
  async function sentEarly(events: AgentEvent[], stores: (c: ConversationDetail) => void = () => {}) {
    const c = backend.create({
      title: "Gửi sớm",
      messages: [storedMessage("user", "chào", { id: "u0" }), storedMessage("assistant", "Chào bạn", { id: "a0" })],
    });
    const load = door();
    const turn = door();
    slow(c.id, { load, turn });
    backend.nextTurn = events;
    await openConversation("Gửi sớm");
    expect(screen.queryByText("Chào bạn")).not.toBeInTheDocument();

    await userEvent.type(screen.getByRole("textbox", { name: vi.composerPlaceholder }), "tin mới{Enter}");
    await waitFor(() => expect(backend.requests.some((r) => r.path.endsWith("/messages"))).toBe(true));
    // The opening load answers now, with the thread as it was before the message: the turn
    // has the thread, so it is put aside and the conversation is read again after the turn.
    await act(async () => load.open());
    expect(screen.queryByText("Chào bạn")).not.toBeInTheDocument();
    expect(userBubble("tin mới")).toBeInTheDocument();
    expect(threadLoads(c.id)).toBe(1);

    stores(c);
    await act(async () => turn.open());
    // What only a load brings: the load the tab owed itself has landed.
    expect(await screen.findByText("Chào bạn")).toBeInTheDocument();
    await act(async () => {});
    expect(threadLoads(c.id)).toBe(2);
    return c;
  }

  it("still says that the turn ended in an error once the conversation has been read again", async () => {
    await sentEarly(ERROR);

    const notice = screen.getByTestId("notice");
    expect(notice).toHaveTextContent(`${vi.errorPrefix}all routes failed`);
    expect(notice).toHaveClass("notice", "error");
    // The message is there once, the server's now, and nothing answers it.
    expect(screen.getAllByTestId("message-user")).toHaveLength(2);
    expect(userBubble("tin mới")).toBeInTheDocument();
    expect(screen.getAllByTestId("message-assistant")).toHaveLength(1);
  });

  it("still says which route the turn went on by once the conversation has been read again", async () => {
    await sentEarly(MOVED, (c) => c.messages.push(storedMessage("assistant", "Đã xong.", { id: "a1" })));

    const notice = screen.getByTestId("notice");
    expect(notice).toHaveTextContent(vi.routeEscalated("error", "fake:echo"));
    expect(notice).toHaveClass("notice", "escalated");
    expect(screen.getAllByText("Đã xong.")).toHaveLength(1);
    expect(screen.getAllByTestId("message-assistant")).toHaveLength(2);
  });

  it("lets go of it when that read brings what came after the turn", async () => {
    // Asked and answered from Telegram while this tab's turn was ending.
    await sentEarly(ERROR, (c) => c.messages.push(storedMessage("user", "hỏi từ Telegram"), storedMessage("assistant", "Trả lời qua Telegram")));

    expect(await screen.findByText("Trả lời qua Telegram")).toBeInTheDocument();
    expect(screen.queryByTestId("notice")).not.toBeInTheDocument();
  });
});

describe("a tab that only read a turn along", () => {
  /** Opens a conversation with a turn going that another channel started, and joins it. */
  async function reading() {
    const c = backend.create({ title: "Đọc theo", messages: [storedMessage("user", "kể chuyện đi", { id: "u0" })] });
    const turn = backend.serveTurn(c.id);
    const load = door();
    const kept: { load?: { shut: Promise<void> } } = {};
    slow(c.id, kept);
    await openConversation("Đọc theo");
    await screen.findByText("kể chuyện đi");
    act(() => stream().emit({ type: "run", run: run(c.id, "running") }));
    await waitFor(() => expect(turn.watchers()).toBe(1));

    /** Ends the turn as `status`, and hands over the load the tab then makes. */
    const ends = async (status: RunInfo["status"]) => {
      const before = threadLoads(c.id);
      kept.load = load;
      await act(async () => turn.end());
      act(() => stream().emit({ type: "run", run: run(c.id, status) }));
      await waitFor(() => expect(threadLoads(c.id)).toBe(before + 1));
      await act(async () => load.open());
      await act(async () => {});
    };
    return { c, turn, ends };
  }

  it("still says that the turn ended in an error once its end has been read back", async () => {
    const { turn, ends } = await reading();
    await act(async () => turn.push(ERROR));
    expect(await screen.findByTestId("notice")).toHaveTextContent(`${vi.errorPrefix}all routes failed`);

    await ends("error");

    expect(screen.getByTestId("notice")).toHaveTextContent(`${vi.errorPrefix}all routes failed`);
    expect(screen.getAllByTestId("message-user")).toHaveLength(1);
    expect(screen.queryByTestId("thinking")).not.toBeInTheDocument();
  });

  it("still says which route the turn went on by once its end has been read back", async () => {
    const { c, turn, ends } = await reading();
    c.messages.push(storedMessage("assistant", "Đã xong.", { id: "a1" }));
    await act(async () => turn.push(MOVED));
    expect(await screen.findByTestId("notice")).toHaveTextContent(vi.routeEscalated("error", "fake:echo"));

    await ends("done");

    expect(screen.getByTestId("notice")).toHaveTextContent(vi.routeEscalated("error", "fake:echo"));
    expect(screen.getAllByTestId("message-assistant")).toHaveLength(1);
  });

  it("lets go of it when another turn is found going in the conversation", async () => {
    const { c, turn, ends } = await reading();
    await act(async () => turn.push(ERROR));
    await ends("error");
    expect(screen.getByTestId("notice")).toBeInTheDocument();

    // A turn with no message of its own, as a job's or one carried on after a restart: the
    // stored thread ends where it did, and what the last turn said is not about this one.
    const next = backend.serveTurn(c.id, { writing: [{ type: "text_delta", text: "Làm lại " }] });
    act(() => stream().emit({ type: "run", run: run(c.id, "running", "r2") }));

    expect(await screen.findByTestId("streaming")).toHaveTextContent("Làm lại");
    expect(screen.queryByTestId("notice")).not.toBeInTheDocument();
    expect(next.watchers()).toBe(1);
  });
});
