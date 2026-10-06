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
});
