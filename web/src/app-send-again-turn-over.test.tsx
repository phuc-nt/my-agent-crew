import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentEvent, ConversationDetail } from "./api/types";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, fakeRun, storedMessage } from "./test/fake-backend";

/**
 * A send the server took, whose answer never reached this tab, and the same words sent again
 * later. While the turn that message got is open they are that message, said once. Once the
 * turn is seen to end they are a new message: the next step the person asks for.
 */

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "";
});

afterEach(() => vitest.unstubAllGlobals());

/** The server takes the next message and the connection drops before it answers. */
function loseAnswer() {
  let lost = false;
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await backend.fetch(input, init);
    if (init?.method !== "POST" || !String(input).endsWith("/messages") || lost) return response;
    lost = true;
    void response.body?.cancel();
    throw new TypeError("Failed to fetch");
  });
}

/** The page on the conversation, its activity stream open on a server where nothing is going. */
async function openConversation(title: string) {
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: new RegExp(title) }));
  await screen.findByRole("heading", { level: 1, name: title });
  const stream = FakeEventSource.instances.at(-1)!;
  act(() => {
    stream.open();
    stream.emit({ type: "snapshot", runs: [] });
  });
  return stream;
}

const box = () => screen.getByRole("textbox", { name: vi.composerPlaceholder });
const sends = (id: string) =>
  backend.requests.filter((r) => r.method === "POST" && r.path === `/conversations/${id}/messages`).map((r) => r.body as { text: string; request_id: string });
/** What the server stored as said by the person, in order. */
const said = (c: ConversationDetail) => c.messages.filter((m) => m.role === "user").map((m) => m.content);
const answer = (content: string, id: string): AgentEvent[] => [
  { type: "assistant_message", message_id: id, content, tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
  { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
];
const going = (id: string, conversation: string) => fakeRun({ id, conversation_id: conversation, source: "chat", status: "running", finished_at: null });
const over = (id: string, conversation: string) => fakeRun({ id, conversation_id: conversation, source: "chat", status: "done" });

/** Sends `text`, and waits for the failure that hands the words back. */
async function sendUnheard(text: string) {
  await userEvent.type(box(), `${text}{Enter}`);
  await waitFor(() => expect(box()).toHaveValue(text));
  expect(screen.getByTestId("notice")).toHaveTextContent(vi.requestErrors.network);
}

describe("a message the server took and whose answer was lost, sent again after its turn", () => {
  it("is a new message once the turn it started was read along with to its end", async () => {
    const c = backend.create({ title: "Bước tiếp" });
    loseAnswer();
    const stream = await openConversation("Bước tiếp");
    await sendUnheard("tiếp tục");
    const turn = backend.serveTurn(c.id, { writing: [{ type: "text_delta", text: "đang làm bước một" }], stoppable: true });
    act(() => stream.emit({ type: "run", run: going("r1", c.id) }));
    expect(await screen.findByTestId("streaming")).toHaveTextContent("đang làm bước một");

    c.messages.push(storedMessage("assistant", "Xong bước một.", { id: "a1" }));
    await act(async () => {
      turn.push(answer("Xong bước một.", "a1"));
      turn.end();
    });
    act(() => stream.emit({ type: "run", run: over("r1", c.id) }));
    await waitFor(() => expect(screen.queryByTestId("streaming")).not.toBeInTheDocument());
    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("Xong bước một.");
    expect(box()).toHaveValue("tiếp tục"); // the words the failed send handed back

    backend.nextTurn = answer("Xong bước hai.", "a2");
    await userEvent.type(box(), "{Enter}");

    await waitFor(() => expect(sends(c.id)).toHaveLength(2));
    expect(sends(c.id)[1].text).toBe("tiếp tục");
    expect(sends(c.id)[1].request_id).toMatch(/^[0-9a-f]{32}$/);
    expect(sends(c.id)[1].request_id).not.toBe(sends(c.id)[0].request_id);
    // The server took it as a message of its own, and the turn it started is read.
    await waitFor(() => expect(screen.getAllByTestId("message-assistant")).toHaveLength(2));
    expect(screen.getAllByTestId("message-assistant")[1]).toHaveTextContent("Xong bước hai.");
    expect(said(c)).toEqual(["tiếp tục", "tiếp tục"]);
    expect(box()).toHaveValue("");
  });

  it("is a new message once the run of that turn is known to be over, though no stream of it was read", async () => {
    const c = backend.create({ title: "Chỉ biết đã xong" });
    loseAnswer();
    const stream = await openConversation("Chỉ biết đã xong");
    await sendUnheard("tiếp tục");
    // The run is known to be going, and the server has no turn there to read along with.
    act(() => stream.emit({ type: "run", run: going("r1", c.id) }));
    await waitFor(() => expect(backend.requests.some((r) => r.method === "GET" && r.path === `/conversations/${c.id}/turn`)).toBe(true));
    expect(screen.queryByTestId("streaming")).not.toBeInTheDocument();

    c.messages.push(storedMessage("assistant", "Xong bước một.", { id: "a1" }));
    act(() => stream.emit({ type: "run", run: over("r1", c.id) }));
    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("Xong bước một.");
    expect(box()).toHaveValue("tiếp tục");

    backend.nextTurn = answer("Xong bước hai.", "a2");
    await userEvent.type(box(), "{Enter}");

    await waitFor(() => expect(sends(c.id)).toHaveLength(2));
    expect(sends(c.id)[1].request_id).not.toBe(sends(c.id)[0].request_id);
    await waitFor(() => expect(screen.getAllByTestId("message-assistant")).toHaveLength(2));
    expect(said(c)).toEqual(["tiếp tục", "tiếp tục"]);
    expect(box()).toHaveValue("");
  });
});

describe("a message the server put in line and whose answer was lost, sent again", () => {
  /** "việc hai" was sent while the turn of "việc một" was going and nothing was heard of it.
   *  That turn has ended since, and the server runs the waiting message in a turn of its own,
   *  which the page reads along with. */
  async function waitingBehind(title: string) {
    const c = backend.create({ title });
    const held = backend.holdTurn(c.id);
    const stream = await openConversation(title);
    await userEvent.type(box(), "việc một{Enter}");
    act(() => stream.emit({ type: "run", run: going("r1", c.id) }));
    await act(async () => held.push([{ type: "text_delta", text: "đang làm việc một" }]));
    expect(await screen.findByTestId("streaming")).toHaveTextContent("đang làm việc một");
    loseAnswer();
    await sendUnheard("việc hai");
    expect(c.queued).toHaveLength(1); // the server holds it; this tab was never told

    c.messages.push(storedMessage("assistant", "Xong việc một.", { id: "a1" }));
    await act(async () => {
      held.push(answer("Xong việc một.", "a1"));
      held.release();
    });
    await waitFor(() => expect(screen.queryByRole("button", { name: vi.stop })).not.toBeInTheDocument());
    backend.drain(c.id);
    const turn = backend.serveTurn(c.id, { writing: [{ type: "text_delta", text: "đang làm việc hai" }], stoppable: true });
    act(() => stream.emit({ type: "run", run: over("r1", c.id) }));
    act(() => stream.emit({ type: "run", run: going("r2", c.id) }));
    expect(await screen.findByTestId("streaming")).toHaveTextContent("đang làm việc hai");
    expect(said(c)).toEqual(["việc một", "việc hai"]);
    expect(box()).toHaveValue("việc hai");
    return { c, stream, turn };
  }

  it("is said once while the turn it waited for is going, though the turn before it has ended", async () => {
    const { c, turn } = await waitingBehind("Đang tới lượt");

    await userEvent.type(box(), "{Enter}");

    await waitFor(() => expect(box()).toHaveValue(""));
    // The second request was let go as soon as the server said the message had arrived.
    await waitFor(() => expect(turn.watchers()).toBe(1));
    expect(sends(c.id)).toHaveLength(3);
    expect(sends(c.id)[2].request_id).toBe(sends(c.id)[1].request_id);
    expect(said(c)).toEqual(["việc một", "việc hai"]);
    expect(screen.getByTestId("streaming")).toHaveTextContent("đang làm việc hai");
  });

  it("is a new message once the turn it waited for has ended too", async () => {
    const { c, stream, turn } = await waitingBehind("Hết lượt chờ");
    c.messages.push(storedMessage("assistant", "Xong việc hai.", { id: "a2" }));
    await act(async () => {
      turn.push(answer("Xong việc hai.", "a2"));
      turn.end();
    });
    act(() => stream.emit({ type: "run", run: over("r2", c.id) }));
    await waitFor(() => expect(screen.queryByTestId("streaming")).not.toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByTestId("message-assistant")).toHaveLength(2));
    expect(box()).toHaveValue("việc hai");

    backend.nextTurn = answer("Xong việc hai lần nữa.", "a3");
    await userEvent.type(box(), "{Enter}");

    await waitFor(() => expect(sends(c.id)).toHaveLength(3));
    expect(sends(c.id)[2].request_id).not.toBe(sends(c.id)[1].request_id);
    await waitFor(() => expect(screen.getAllByTestId("message-assistant")).toHaveLength(3));
    expect(said(c)).toEqual(["việc một", "việc hai", "việc hai"]);
    expect(box()).toHaveValue("");
  });
});
