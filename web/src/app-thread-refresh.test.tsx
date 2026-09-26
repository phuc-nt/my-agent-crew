import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { RunInfo } from "./api/types";
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

/** A run of the open conversation that Telegram started, in the state the test names. */
function telegramRun(conversationId: string, status: RunInfo["status"]): RunInfo {
  const live = status === "running" || status === "awaiting_approval";
  return fakeRun({ id: "tg", conversation_id: conversationId, source: "telegram", status, finished_at: live ? null : "2026-09-19T08:00:05Z" });
}

const threadLoads = (id: string) =>
  backend.requests.filter((r) => r.method === "GET" && r.path === `/conversations/${id}`).length;

async function openConversation(title: string) {
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: new RegExp(title) }));
  await screen.findByRole("heading", { level: 1, name: title });
  act(() => {
    stream().open();
    stream().emit({ type: "snapshot", runs: [] });
  });
}

describe("the open thread and runs this tab did not stream", () => {
  it("shows a run started elsewhere and reloads the thread once when it finishes", async () => {
    const c = backend.create({ title: "Từ Telegram", messages: [storedMessage("user", "chào")] });
    await openConversation("Từ Telegram");

    act(() => stream().emit({ type: "run", run: telegramRun(c.id, "running") }));
    expect(screen.getByTestId("thinking")).toBeInTheDocument();

    c.messages.push(storedMessage("assistant", "Trả lời gửi qua Telegram"));
    const before = threadLoads(c.id);
    act(() => stream().emit({ type: "run", run: telegramRun(c.id, "done") }));

    expect(await screen.findByText("Trả lời gửi qua Telegram")).toBeInTheDocument();
    expect(screen.queryByTestId("thinking")).not.toBeInTheDocument();
    // Settle any stray effects before counting: one finish is one reload.
    await act(async () => {});
    expect(threadLoads(c.id)).toBe(before + 1);
  });

  it("reloads when a run elsewhere stops for an approval, so the decision is offered here", async () => {
    const c = backend.create({ title: "Chờ duyệt", messages: [storedMessage("user", "ghi tệp")] });
    await openConversation("Chờ duyệt");
    act(() => stream().emit({ type: "run", run: telegramRun(c.id, "running") }));

    c.messages.push(storedMessage("assistant", "", { tool_calls: [{ id: "tc", name: "write_file", arguments: {} }] }));
    c.pending_approval = { id: "ap", conversation_id: c.id, message_id: "m", tool_call_id: "tc", tool_name: "write_file", arguments: {}, status: "pending", created_at: "", expires_at: null, resolved_at: null };
    c.status = "awaiting_approval";
    act(() => stream().emit({ type: "event", run_id: "tg", agent_id: "default", conversation_id: c.id, status: "awaiting_approval", event: { type: "approval_required", approval_id: "ap", tool_call_id: "tc", name: "write_file", arguments: {}, reason: "", expires_at: "" } }));

    expect(await screen.findByRole("alertdialog", { name: vi.awaitingApproval })).toBeInTheDocument();
  });

  it("reloads once the stream is back when a run started and ended while it was down", async () => {
    const c = backend.create({ title: "Trong lúc mất", messages: [storedMessage("user", "chào")] });
    await openConversation("Trong lúc mất");
    act(() => stream().onerror?.());

    c.messages.push(storedMessage("assistant", "Trả lời lúc mất kết nối"));
    backend.runs = [telegramRun(c.id, "done")];
    const before = threadLoads(c.id);
    await userEvent.click(screen.getByRole("button", { name: vi.streamRetryLabel }));
    act(() => {
      stream().open();
      stream().emit({ type: "snapshot", runs: [] });
    });

    expect(await screen.findByText("Trả lời lúc mất kết nối")).toBeInTheDocument();
    await act(async () => {});
    expect(threadLoads(c.id)).toBe(before + 1);
  });

  it("lets go of a run seen live that ended while the stream was down", async () => {
    const c = backend.create({ title: "Kết thúc lúc mất", messages: [storedMessage("user", "chào")] });
    await openConversation("Kết thúc lúc mất");
    act(() => stream().emit({ type: "run", run: telegramRun(c.id, "running") }));
    expect(screen.getByTestId("thinking")).toBeInTheDocument();
    act(() => stream().onerror?.());

    // The browser's own retry: the snapshot is all this page hears of the finish.
    c.messages.push(storedMessage("assistant", "Xong khi đang mất"));
    backend.runs = [telegramRun(c.id, "done")];
    const before = threadLoads(c.id);
    act(() => {
      stream().open();
      stream().emit({ type: "snapshot", runs: [] });
    });

    expect(await screen.findByText("Xong khi đang mất")).toBeInTheDocument();
    expect(screen.queryByTestId("thinking")).not.toBeInTheDocument();
    await act(async () => {});
    expect(threadLoads(c.id)).toBe(before + 1);
  });

  it("leaves this tab's own turn alone when its run finishes after the stream did", async () => {
    const c = backend.create({ title: "Của tab này" });
    let release = () => {};
    const gate = new Promise<void>((resolve) => (release = resolve));
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/messages")) await gate;
      return backend.fetch(input, init);
    });
    backend.nextTurn = [
      { type: "assistant_message", message_id: "a1", content: "Xong", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
      { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
    ];
    await openConversation("Của tab này");

    await userEvent.type(screen.getByRole("textbox", { name: vi.composerPlaceholder }), "làm đi{Enter}");
    act(() => stream().emit({ type: "run", run: { ...telegramRun(c.id, "running"), source: "chat" } }));
    await act(async () => release());
    await screen.findByText("Xong");

    const before = threadLoads(c.id);
    act(() => stream().emit({ type: "run", run: { ...telegramRun(c.id, "done"), source: "chat" } }));
    await act(async () => {});
    expect(threadLoads(c.id)).toBe(before);
  });

  it("stops a call left spinning once the stream says nothing is running here", async () => {
    backend.create({
      title: "Bị cắt",
      messages: [storedMessage("assistant", "", { tool_calls: [{ id: "tc", name: "shell_run", arguments: {} }] })],
    });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Bị cắt/ }));
    const card = await screen.findByTestId("tool-card");
    expect(card).toHaveTextContent(vi.toolRunning);

    act(() => {
      stream().open();
      stream().emit({ type: "snapshot", runs: [] });
    });
    expect(card).toHaveTextContent(vi.toolStopped);
    expect(card.querySelector(".tool-status.running")).toBeNull();
  });
});

describe("the live stream's pill", () => {
  it("offers a retry when the stream drops, and the retry opens a fresh stream", async () => {
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));
    const line = screen.getByTestId("status-line");
    expect(line).toHaveTextContent(vi.streamConnecting);
    expect(within(line).queryByRole("button")).toBeNull();

    const first = stream();
    act(() => first.onerror?.());
    expect(line).toHaveTextContent(vi.streamDisconnected);
    await userEvent.click(within(line).getByRole("button", { name: vi.streamRetryLabel }));

    expect(first.closed).toBe(true);
    expect(stream()).not.toBe(first);
    act(() => stream().open());
    expect(line).toHaveTextContent(vi.streamConnected);
    expect(within(line).queryByRole("button")).toBeNull();
  });

  it("says the device is offline instead of offering a retry that cannot work", async () => {
    const onLine = vitest.spyOn(window.navigator, "onLine", "get").mockReturnValue(false);
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));
    act(() => stream().onerror?.());
    const line = screen.getByTestId("status-line");
    expect(line).toHaveTextContent(vi.streamOffline);
    expect(within(line).queryByRole("button")).toBeNull();

    onLine.mockReturnValue(true);
    act(() => {
      window.dispatchEvent(new Event("online"));
    });
    expect(within(line).getByRole("button", { name: vi.streamRetryLabel })).toBeInTheDocument();
    onLine.mockRestore();
  });
});
