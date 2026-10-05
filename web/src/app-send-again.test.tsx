import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentEvent } from "./api/types";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, fakeRun, storedMessage } from "./test/fake-backend";

/**
 * A send the server took, whose answer never reached this tab. The words go back to the box,
 * as for any send nothing was heard of, and sending them again must not say them twice.
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

/** The server takes the next `count` messages and the connection drops before it answers. */
function loseAnswers(count = 1) {
  let left = count;
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await backend.fetch(input, init);
    if (init?.method !== "POST" || !String(input).endsWith("/messages") || left === 0) return response;
    left -= 1;
    void response.body?.cancel();
    throw new TypeError("Failed to fetch");
  });
}

async function openConversation(title: string) {
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: new RegExp(title) }));
  await screen.findByRole("heading", { level: 1, name: title });
}

const box = () => screen.getByRole("textbox", { name: vi.composerPlaceholder });
const bubbles = () => screen.queryAllByTestId("message-user").map((b) => b.querySelector("p")?.textContent);
const sends = (id: string) =>
  backend.requests.filter((r) => r.method === "POST" && r.path === `/conversations/${id}/messages`).map((r) => r.body as { text: string; request_id: string });
const answer = (content: string): AgentEvent[] => [
  { type: "assistant_message", message_id: "a1", content, tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
  { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
];

/** Sends `text`, and waits for the failure that hands the words back. */
async function sendUnheard(text: string) {
  await userEvent.type(box(), `${text}{Enter}`);
  await waitFor(() => expect(box()).toHaveValue(text));
  expect(screen.getByTestId("notice")).toHaveTextContent(vi.requestErrors.network);
}

describe("a message the server took, sent again because its answer was lost", () => {
  it("is shown once with the answer it already got, and starts no second turn", async () => {
    const c = backend.create({ title: "Rớt mạng" });
    loseAnswers();
    await openConversation("Rớt mạng");
    await sendUnheard("làm đi");
    expect(bubbles()).toEqual([]);
    // The turn ran to its end on the server, with nobody reading it.
    c.messages.push(storedMessage("assistant", "Xong rồi.", { id: "a1" }));

    await userEvent.type(box(), "{Enter}");

    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("Xong rồi.");
    await waitFor(() => expect(box()).toHaveValue(""));
    expect(bubbles()).toEqual(["làm đi"]);
    expect(c.messages.filter((m) => m.role === "user")).toHaveLength(1);
    expect(sends(c.id)).toHaveLength(2);
    expect(sends(c.id)[1]).toEqual(sends(c.id)[0]);
    expect(sends(c.id)[0].request_id).toMatch(/^[0-9a-f]{32}$/);
    expect(screen.queryByTestId("thinking")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: vi.stop })).not.toBeInTheDocument();
  });

  it("joins the turn still going, and follows it to its end", async () => {
    const c = backend.create({ title: "Đang làm dở" });
    loseAnswers();
    await openConversation("Đang làm dở");
    await sendUnheard("kể chuyện đi");
    const turn = backend.serveTurn(c.id, { writing: [{ type: "text_delta", text: "Ngày xửa " }], stoppable: true });

    await userEvent.type(box(), "{Enter}");

    expect(await screen.findByTestId("streaming")).toHaveTextContent("Ngày xửa");
    expect(box()).toHaveValue("");
    expect(bubbles()).toEqual(["kể chuyện đi"]);
    expect(turn.watchers()).toBe(1);
    expect(screen.getByRole("button", { name: vi.stop })).toBeInTheDocument(); // the person's own turn

    c.messages.push(storedMessage("assistant", "Ngày xửa ngày xưa.", { id: "a1" }));
    await act(async () => {
      turn.push(answer("Ngày xửa ngày xưa."));
      turn.end();
    });
    await waitFor(() => expect(screen.queryByTestId("streaming")).not.toBeInTheDocument());
    expect(screen.getAllByTestId("message-assistant")).toHaveLength(1);
    expect(bubbles()).toEqual(["kể chuyện đi"]);
    expect(c.messages.filter((m) => m.role === "user")).toHaveLength(1);
    expect(sends(c.id)[1].request_id).toBe(sends(c.id)[0].request_id);
  });

  it("changes nothing on a screen that already reads the turn it started", async () => {
    const c = backend.create({ title: "Đã xem lại" });
    loseAnswers();
    await openConversation("Đã xem lại");
    const stream = FakeEventSource.instances.at(-1)!;
    act(() => {
      stream.open();
      stream.emit({ type: "snapshot", runs: [] });
    });
    await sendUnheard("làm đi");
    const turn = backend.serveTurn(c.id, { writing: [{ type: "text_delta", text: "đang làm" }], stoppable: true });
    // The run is known to be going, so the tab reads along with it by itself.
    act(() => stream.emit({ type: "run", run: fakeRun({ id: "r1", conversation_id: c.id, source: "chat", status: "running", finished_at: null }) }));
    expect(await screen.findByTestId("streaming")).toHaveTextContent("đang làm");
    expect(bubbles()).toEqual(["làm đi"]);
    expect(box()).toHaveValue("làm đi"); // still there to send again

    await userEvent.type(box(), "{Enter}");

    await waitFor(() => expect(box()).toHaveValue(""));
    // The second request was let go as soon as the server said the message had arrived.
    await waitFor(() => expect(turn.watchers()).toBe(1));
    expect(screen.getByTestId("streaming")).toHaveTextContent("đang làm");
    expect(bubbles()).toEqual(["làm đi"]);
    expect(screen.queryByRole("list", { name: vi.queuedLabel })).not.toBeInTheDocument();
    expect(c.messages.filter((m) => m.role === "user")).toHaveLength(1);
    expect(sends(c.id)[1].request_id).toBe(sends(c.id)[0].request_id);
  });

  it("keeps its one place in line when it was waiting behind a turn", async () => {
    const c = backend.create({ title: "Xếp hàng" });
    const held = backend.holdTurn(c.id);
    await openConversation("Xếp hàng");
    await userEvent.type(box(), "việc một{Enter}");
    await act(async () => held.push([{ type: "text_delta", text: "đang làm việc một" }]));
    await waitFor(() => expect(box()).toHaveValue(""));
    expect(bubbles()).toEqual(["việc một"]);
    loseAnswers();
    await sendUnheard("việc hai");
    expect(c.queued).toHaveLength(1); // the server holds it; this tab was never told
    expect(screen.queryByRole("list", { name: vi.queuedLabel })).not.toBeInTheDocument();

    await userEvent.type(box(), "{Enter}");

    const chips = await screen.findByRole("list", { name: vi.queuedLabel });
    await waitFor(() => expect(box()).toHaveValue(""));
    expect(within(chips).getAllByRole("listitem")).toHaveLength(1);
    expect(chips).toHaveTextContent("việc hai");
    expect(c.queued).toHaveLength(1);
    expect(sends(c.id)[2].request_id).toBe(sends(c.id)[1].request_id);
    expect(sends(c.id)[1].request_id).not.toBe(sends(c.id)[0].request_id);
    await act(async () => held.release());
  });
});

describe("a message sent again that the server never had", () => {
  it("is taken as any new message is", async () => {
    const c = backend.create({ title: "Chưa tới" });
    // The connection failed before the request reached the server at all.
    let failing = true;
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      if (failing && init?.method === "POST" && String(input).endsWith("/messages")) throw new TypeError("Failed to fetch");
      return backend.fetch(input, init);
    });
    await openConversation("Chưa tới");
    await sendUnheard("chào");
    expect(c.messages).toEqual([]);
    failing = false;
    backend.nextTurn = answer("Chào bạn.");

    await userEvent.type(box(), "{Enter}");

    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("Chào bạn.");
    expect(bubbles()).toEqual(["chào"]);
    expect(c.messages.filter((m) => m.role === "user")).toHaveLength(1);
    expect(box()).toHaveValue("");
  });
});
