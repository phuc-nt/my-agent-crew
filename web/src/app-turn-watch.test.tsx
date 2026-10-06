import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentEvent, RunInfo } from "./api/types";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, fakeRun, storedMessage } from "./test/fake-backend";

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

function run(conversationId: string, source: RunInfo["source"], status: RunInfo["status"] = "running"): RunInfo {
  return fakeRun({ id: "r1", conversation_id: conversationId, source, status, finished_at: status === "running" ? null : "2026-10-06T08:00:05Z" });
}

const asked = (id: string, what: "turn" | "stop" | "") =>
  backend.requests.filter((r) => r.path === `/conversations/${id}${what && `/${what}`}`).length;

const answer = (content: string): AgentEvent[] => [
  { type: "assistant_message", message_id: "a1", content, tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
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

describe("a turn under way that this tab did not start", () => {
  it("is shown as it is written and followed to its end, with nothing drawn twice", async () => {
    const c = backend.create({ title: "Từ Telegram", messages: [storedMessage("user", "kể chuyện đi")] });
    const turn = backend.serveTurn(c.id, { writing: [{ type: "text_delta", text: "Ngày xửa " }] });
    await openConversation("Từ Telegram");

    act(() => stream().emit({ type: "run", run: run(c.id, "telegram") }));
    expect(await screen.findByTestId("streaming")).toHaveTextContent("Ngày xửa");
    // It is the bot's turn: there to read, not this tab's to end.
    expect(screen.queryByRole("button", { name: vi.stop })).not.toBeInTheDocument();

    await act(async () => turn.push([{ type: "text_delta", text: "ngày xưa" }]));
    expect(screen.getByTestId("streaming")).toHaveTextContent("Ngày xửa ngày xưa");

    c.messages.push(storedMessage("assistant", "Ngày xửa ngày xưa.", { id: "a1" }));
    await act(async () => {
      turn.push(answer("Ngày xửa ngày xưa."));
      turn.end();
    });
    act(() => stream().emit({ type: "run", run: run(c.id, "telegram", "done") }));
    await waitFor(() => expect(screen.queryByTestId("streaming")).not.toBeInTheDocument());
    await act(async () => {});
    expect(screen.getAllByTestId("message-assistant")).toHaveLength(1);
    expect(screen.getAllByTestId("message-user")).toHaveLength(1);
    expect(screen.queryByTestId("thinking")).not.toBeInTheDocument();
    expect(asked(c.id, "turn")).toBe(1);
  });

  it("goes on while the person is in another conversation, and is picked up again on the way back", async () => {
    const written: AgentEvent[] = [{ type: "text_delta", text: "phần một" }];
    const c = backend.create({ title: "Đang chạy", messages: [storedMessage("user", "làm đi")] });
    backend.create({ title: "Cuộc khác" });
    const turn = backend.serveTurn(c.id, { writing: written, stoppable: true });
    await openConversation("Đang chạy");
    act(() => stream().emit({ type: "run", run: run(c.id, "chat") }));
    expect(await screen.findByTestId("streaming")).toHaveTextContent("phần một");
    expect(turn.watchers()).toBe(1);

    await userEvent.click(screen.getByRole("button", { name: /Cuộc khác/ }));
    await screen.findByRole("heading", { level: 1, name: "Cuộc khác" });
    await waitFor(() => expect(turn.watchers()).toBe(0));
    expect(asked(c.id, "stop")).toBe(0); // leaving is not stopping
    expect(screen.queryByTestId("streaming")).not.toBeInTheDocument();

    written[0] = { type: "text_delta", text: "phần một, phần hai" }; // the turn kept writing
    await userEvent.click(screen.getByRole("button", { name: /Đang chạy/ }));
    await screen.findByRole("heading", { level: 1, name: "Đang chạy" });
    expect(await screen.findByTestId("streaming")).toHaveTextContent("phần một, phần hai");
    expect(turn.watchers()).toBe(1);
    expect(screen.getAllByTestId("message-user")).toHaveLength(1);
  });

  it("is stopped from here when the server reads it itself", async () => {
    const c = backend.create({ title: "Tab khác gửi", messages: [storedMessage("user", "làm đi")] });
    const turn = backend.serveTurn(c.id, { writing: [{ type: "text_delta", text: "đang viết" }], stoppable: true });
    await openConversation("Tab khác gửi");
    act(() => stream().emit({ type: "run", run: run(c.id, "chat") }));
    await screen.findByTestId("streaming");

    await userEvent.click(screen.getByRole("button", { name: vi.stop }));
    expect(await screen.findByTestId("notice")).toHaveTextContent(vi.stopped);
    expect(screen.queryByTestId("streaming")).not.toBeInTheDocument();
    expect(turn.watchers()).toBe(0);
    expect(asked(c.id, "stop")).toBe(1);
  });

  it("is still said to have been stopped once its run has ended and the conversation has been read again", async () => {
    const c = backend.create({ title: "Dừng khi đang xem", messages: [storedMessage("user", "làm đi")] });
    backend.serveTurn(c.id, { writing: [{ type: "text_delta", text: "đang viết" }], stoppable: true });
    await openConversation("Dừng khi đang xem");
    act(() => stream().emit({ type: "run", run: run(c.id, "chat") }));
    await screen.findByTestId("streaming");
    await userEvent.click(screen.getByRole("button", { name: vi.stop }));
    expect(await screen.findByTestId("notice")).toHaveTextContent(vi.stopped);

    // The turn was never this tab's own, so its run ending makes the tab read the conversation
    // again. What the server stored as the turn stopped comes only with that read.
    c.messages.push(storedMessage("assistant", "phần đã viết", { id: "a1" }));
    act(() => stream().emit({ type: "run", run: { ...run(c.id, "chat", "error"), summary: "interrupted" } }));
    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("phần đã viết");
    expect(screen.getByTestId("notice")).toHaveTextContent(vi.stopped);
    expect(screen.queryByTestId("thinking")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: vi.stop })).not.toBeInTheDocument();
  });

  it("is not joined again while the server lets go of a turn it ended on this tab's Stop", async () => {
    const c = backend.create({ title: "Dừng giữa lệnh", messages: [storedMessage("user", "làm đi")] });
    const turn = backend.serveTurn(c.id, { writing: [{ type: "text_delta", text: "đang viết" }], stoppable: true });
    // The server says at once that it ended the turn, which is there to join a while longer:
    // it has a script to kill, a call to close, before its run is said to be over.
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      if (!String(input).endsWith("/stop") || init?.method !== "POST") return backend.fetch(input, init);
      return new Response(JSON.stringify({ cleared: [], cancelled: true }), { status: 200, headers: { "content-type": "application/json" } });
    });
    await openConversation("Dừng giữa lệnh");
    act(() => stream().emit({ type: "run", run: run(c.id, "chat") }));
    await screen.findByTestId("streaming");
    await userEvent.click(screen.getByRole("button", { name: vi.stop }));
    expect(await screen.findByTestId("notice")).toHaveTextContent(vi.stopped);
    await waitFor(() => expect(turn.watchers()).toBe(0));

    // The run's end and the read it causes come after anything the tab did on being told.
    c.messages.push(storedMessage("assistant", "phần đã viết", { id: "a1" }));
    act(() => stream().emit({ type: "run", run: { ...run(c.id, "chat", "error"), summary: "interrupted" } }));
    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("phần đã viết");
    expect(asked(c.id, "turn")).toBe(1);
    expect(turn.watchers()).toBe(0);
    expect(screen.getByTestId("notice")).toHaveTextContent(vi.stopped);
    expect(screen.queryByTestId("streaming")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: vi.stop })).not.toBeInTheDocument();
  });

  it("is still said to be going when the server has nothing of it to read, and is asked about once", async () => {
    const c = backend.create({ title: "Vừa xong", messages: [storedMessage("user", "chào")] });
    await openConversation("Vừa xong");
    act(() => stream().emit({ type: "run", run: run(c.id, "telegram") }));
    await waitFor(() => expect(asked(c.id, "turn")).toBe(1));
    act(() => stream().emit({ type: "run", run: { ...run(c.id, "telegram"), spent_usd: 0.01 } }));
    await act(async () => {});
    expect(screen.getByTestId("thinking")).toBeInTheDocument();
    expect(screen.queryByTestId("notice")).not.toBeInTheDocument();
    expect(asked(c.id, "turn")).toBe(1);
  });
});

describe("a turn this tab started", () => {
  it("is read on the stream that started it, and not watched as well", async () => {
    const c = backend.create({ title: "Của tab này" });
    const turn = backend.holdTurn(c.id);
    await openConversation("Của tab này");
    await userEvent.type(screen.getByRole("textbox", { name: vi.composerPlaceholder }), "làm đi{Enter}");
    act(() => stream().emit({ type: "run", run: run(c.id, "chat") }));
    await act(async () => turn.push([{ type: "text_delta", text: "đang trả lời" }]));
    expect(screen.getByTestId("streaming")).toHaveTextContent("đang trả lời");
    await act(async () => {});
    expect(asked(c.id, "turn")).toBe(0);
    await act(async () => turn.release());
  });

  it("is picked up by watching when the stream that started it is lost and the turn goes on", async () => {
    const c = backend.create({ title: "Rớt mạng" });
    const encoder = new TextEncoder();
    let lost: ReadableStreamDefaultController<Uint8Array> | null = null;
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      if (!String(input).endsWith("/messages") || init?.method !== "POST") return backend.fetch(input, init);
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          lost = controller;
          controller.enqueue(encoder.encode(`event: text_delta\r\ndata: ${JSON.stringify({ type: "text_delta", text: "nửa " })}\r\n\r\n`));
        },
      });
      return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
    });
    await openConversation("Rớt mạng");
    await userEvent.type(screen.getByRole("textbox", { name: vi.composerPlaceholder }), "làm đi{Enter}");
    act(() => stream().emit({ type: "run", run: run(c.id, "chat") }));
    expect(await screen.findByTestId("streaming")).toHaveTextContent("nửa");
    expect(asked(c.id, "turn")).toBe(0);

    // The server stored the message and kept the turn going; only this tab's reading broke.
    c.messages.push(storedMessage("user", "làm đi"));
    const turn = backend.serveTurn(c.id, { writing: [{ type: "text_delta", text: "nửa câu sau" }], stoppable: true });
    await act(async () => lost?.error(new TypeError("network error")));

    await waitFor(() => expect(turn.watchers()).toBe(1));
    expect(await screen.findByTestId("streaming")).toHaveTextContent("nửa câu sau");
    expect(screen.getAllByTestId("message-user")).toHaveLength(1);
    expect(screen.queryByTestId("notice")).not.toBeInTheDocument(); // the turn is fine, and on screen
    expect(screen.getByRole("button", { name: vi.stop })).toBeInTheDocument(); // still this person's to end
  });

  /** The answer to this tab's send in the test's hands — what it says and when it ends — and
   *  a server that can be made to stop answering anything at all. */
  function ownStream() {
    const encoder = new TextEncoder();
    let body: ReadableStreamDefaultController<Uint8Array> | null = null;
    let down = false;
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      if (down) throw new TypeError("Failed to fetch");
      if (!String(input).endsWith("/messages") || init?.method !== "POST") return backend.fetch(input, init);
      const stream = new ReadableStream<Uint8Array>({ start: (controller) => void (body = controller) });
      return new Response(stream, { status: 200, headers: { "content-type": "text/event-stream" } });
    });
    return {
      say: (events: AgentEvent[]) => {
        for (const e of events) body?.enqueue(encoder.encode(`event: ${e.type}\r\ndata: ${JSON.stringify(e)}\r\n\r\n`));
      },
      end: () => body?.close(),
      serverDown: (gone: boolean) => void (down = gone),
    };
  }

  /** Sends a message whose run is seen to start, and has the turn write its first words. */
  async function sendAndRead(conversationId: string, own: ReturnType<typeof ownStream>) {
    await userEvent.type(screen.getByRole("textbox", { name: vi.composerPlaceholder }), "làm đi{Enter}");
    act(() => stream().emit({ type: "run", run: run(conversationId, "chat") }));
    await act(async () => own.say([{ type: "text_delta", text: "nửa " }]));
    expect(await screen.findByTestId("streaming")).toHaveTextContent("nửa");
  }

  it.each<[string, ("stream" | "activity")[]]>([
    ["its stream ends before the activity stream drops", ["stream", "activity"]],
    ["the activity stream drops before its stream ends", ["activity", "stream"]],
  ])("is followed to its end on the server that carries it on after a restart: %s", async (_name, order) => {
    const c = backend.create({ title: "Khởi động lại" });
    const own = ownStream();
    await openConversation("Khởi động lại");
    await sendAndRead(c.id, own);

    // A server told to go ends the stream with no last word and no error, and is gone.
    c.messages.push(storedMessage("user", "làm đi"));
    own.serverDown(true);
    const leaves = { stream: () => own.end(), activity: () => stream().onerror?.() };
    for (const step of order) await act(async () => leaves[step]());
    await waitFor(() => expect(screen.queryByTestId("streaming")).not.toBeInTheDocument());
    expect(screen.queryByTestId("notice")).not.toBeInTheDocument(); // nothing failed that the person can act on

    // The next server carries the same run on, and the tab hears of it once it answers again.
    const turn = backend.serveTurn(c.id, { writing: [{ type: "text_delta", text: "nửa câu sau" }], stoppable: true });
    own.serverDown(false);
    act(() => {
      stream().open();
      stream().emit({ type: "snapshot", runs: [{ ...run(c.id, "chat"), resumed: true }] });
    });
    await waitFor(() => expect(turn.watchers()).toBe(1));
    expect(await screen.findByTestId("streaming")).toHaveTextContent("nửa câu sau");
    expect(screen.getByRole("button", { name: vi.stop })).toBeInTheDocument(); // still this person's to end

    c.messages.push(storedMessage("assistant", "Nửa câu sau, hết.", { id: "a1" }));
    await act(async () => {
      turn.push(answer("Nửa câu sau, hết."));
      turn.end();
    });
    act(() => stream().emit({ type: "run", run: run(c.id, "chat", "done") }));
    await waitFor(() => expect(screen.queryByTestId("streaming")).not.toBeInTheDocument());
    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("Nửa câu sau, hết.");
    await act(async () => {});
    expect(screen.getAllByTestId("message-assistant")).toHaveLength(1);
    expect(screen.getAllByTestId("message-user")).toHaveLength(1);
    expect(screen.queryByTestId("thinking")).not.toBeInTheDocument();
    expect(screen.queryByTestId("notice")).not.toBeInTheDocument();
  });

  it("is asked about once when its stream ends before the turn's last word, and ends there when the server has no turn under way", async () => {
    const c = backend.create({ title: "Dừng ở nơi khác" });
    const own = ownStream();
    await openConversation("Dừng ở nơi khác");
    await sendAndRead(c.id, own);

    // Someone stopped the turn elsewhere: the server ends the stream with no last word.
    c.messages.push(storedMessage("user", "làm đi"));
    await act(async () => own.end());
    await waitFor(() => expect(asked(c.id, "turn")).toBe(1));
    act(() => stream().emit({ type: "run", run: { ...run(c.id, "chat", "error"), summary: "interrupted" } }));
    await waitFor(() => expect(screen.queryByTestId("thinking")).not.toBeInTheDocument());
    await act(async () => {});
    expect(screen.queryByTestId("streaming")).not.toBeInTheDocument();
    expect(screen.queryByTestId("notice")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: vi.stop })).not.toBeInTheDocument();
    expect(screen.getAllByTestId("message-user")).toHaveLength(1);
    expect(asked(c.id, "turn")).toBe(1);
  });

  it("is not asked about when its stream ended on the turn's last word, though its run is said to be going a while longer", async () => {
    const c = backend.create({ title: "Xong trước" });
    const own = ownStream();
    await openConversation("Xong trước");
    await sendAndRead(c.id, own);

    c.messages.push(storedMessage("user", "làm đi"), storedMessage("assistant", "Nửa câu sau, hết.", { id: "a1" }));
    await act(async () => {
      own.say(answer("Nửa câu sau, hết."));
      own.end();
    });
    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("Nửa câu sau, hết.");
    await act(async () => {});
    expect(screen.queryByTestId("thinking")).not.toBeInTheDocument();
    const loads = asked(c.id, "");
    act(() => stream().emit({ type: "run", run: run(c.id, "chat", "done") }));
    await act(async () => {});
    expect(asked(c.id, "turn")).toBe(0);
    expect(asked(c.id, "")).toBe(loads); // read to its end on its own stream: nothing to load again
  });
});
