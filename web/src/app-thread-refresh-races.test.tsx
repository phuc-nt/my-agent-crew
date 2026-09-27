import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { AgentEvent, RunInfo } from "./api/types";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, fakeApproval, fakeRun, storedMessage } from "./test/fake-backend";

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

function run(conversationId: string, status: RunInfo["status"], source = "telegram", id = "r1"): RunInfo {
  const live = status === "running" || status === "awaiting_approval";
  return fakeRun({ id, conversation_id: conversationId, source, status, finished_at: live ? null : "2026-09-19T08:00:05Z" });
}

/** A door the test opens by hand: the fetch behind it answers only then. */
function door() {
  let open = () => {};
  const shut = new Promise<void>((resolve) => (open = resolve));
  return { shut, open };
}

const threadLoads = (id: string) =>
  backend.requests.filter((r) => r.method === "GET" && r.path === `/conversations/${id}`).length;

async function openConversation(title: string, runs: RunInfo[] = []) {
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: new RegExp(title) }));
  await screen.findByRole("heading", { level: 1, name: title });
  act(() => {
    stream().open();
    stream().emit({ type: "snapshot", runs });
  });
}

describe("reloads of the open thread racing this tab's turns and other runs", () => {
  it("keeps a message sent while a reload was on its way, and loads what it missed after the turn", async () => {
    const c = backend.create({ title: "Gửi giữa chừng", messages: [storedMessage("user", "chào")] });
    const load = door();
    const turn = door();
    let holdLoads = false;
    // Each answer is taken when the request arrives and handed over when its door opens,
    // as a slow phone connection would: the reload carries the thread as it was then.
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      const response = await backend.fetch(input, init);
      const path = String(input);
      if (path.endsWith("/messages")) await turn.shut;
      else if (holdLoads && !init?.method && path.endsWith(`/conversations/${c.id}`)) await load.shut;
      return response;
    });
    backend.nextTurn = [
      { type: "assistant_message", message_id: "a1", content: "Đã nhận", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
      { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
    ];
    await openConversation("Gửi giữa chừng");

    act(() => stream().emit({ type: "run", run: run(c.id, "running") }));
    c.messages.push(storedMessage("assistant", "Trả lời qua Telegram"));
    holdLoads = true;
    act(() => stream().emit({ type: "run", run: run(c.id, "done") }));
    await userEvent.type(screen.getByRole("textbox", { name: vi.composerPlaceholder }), "tin mới{Enter}");
    expect(screen.getByText("tin mới")).toBeInTheDocument();

    await act(async () => load.open());
    expect(screen.getByText("tin mới")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: vi.stop })).toBeInTheDocument();

    c.messages.push(storedMessage("assistant", "Đã nhận"));
    await act(async () => turn.open());
    expect(await screen.findByText("Trả lời qua Telegram")).toBeInTheDocument();
    expect(screen.getByText("tin mới")).toBeInTheDocument();
    expect(screen.getByText("Đã nhận")).toBeInTheDocument();
  });

  it("leaves a call spinning while the stream says a run is still going here", async () => {
    const c = backend.create({
      title: "Đang chạy",
      messages: [storedMessage("assistant", "", { tool_calls: [{ id: "tc", name: "shell_run", arguments: {} }] })],
    });
    await openConversation("Đang chạy", [run(c.id, "running")]);

    const card = await screen.findByTestId("tool-card");
    await act(async () => {});
    expect(card).toHaveTextContent(vi.toolRunning);
    expect(card).not.toHaveTextContent(vi.toolStopped);
  });

  it("reloads once when a pause of this tab's own turn is decided on another device", async () => {
    const c = backend.create({ title: "Dừng chờ duyệt", messages: [storedMessage("user", "chào")] });
    const turn = door();
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      const response = await backend.fetch(input, init);
      if (String(input).endsWith("/messages")) await turn.shut;
      return response;
    });
    backend.nextTurn = [
      { type: "assistant_message", message_id: "a1", content: "", tool_calls: [{ id: "tc", name: "write_file", arguments: {} }], provider: "fake", model: "echo", cost_usd: 0 },
      { type: "approval_required", approval_id: "ap", tool_call_id: "tc", name: "write_file", arguments: {}, reason: "", expires_at: "" },
    ];
    await openConversation("Dừng chờ duyệt");

    await userEvent.type(screen.getByRole("textbox", { name: vi.composerPlaceholder }), "ghi tệp{Enter}");
    // The stream reports the run while this tab is still streaming it, so it is this tab's.
    act(() => stream().emit({ type: "run", run: run(c.id, "running", "chat") }));
    await act(async () => turn.open());
    expect(await screen.findByRole("alertdialog", { name: vi.awaitingApproval })).toBeInTheDocument();
    act(() => stream().emit({ type: "run", run: run(c.id, "awaiting_approval", "chat") }));
    await act(async () => {});

    const before = threadLoads(c.id);
    act(() => stream().emit({ type: "run", run: run(c.id, "running", "chat") }));
    await act(async () => {});
    expect(threadLoads(c.id)).toBe(before + 1);
  });
});

/** Holds every chat stream this tab opens until the test lets it through. */
function holdTurns(): () => Promise<void> {
  const turn = door();
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await backend.fetch(input, init);
    if (/\/(messages|approvals\/.*)$/.test(String(input))) await turn.shut;
    return response;
  });
  return async () => act(async () => turn.open());
}

const webTurn: AgentEvent[] = [
  { type: "assistant_message", message_id: "a1", content: "Đã nhận", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
  { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
];

describe("runs of other channels overlapping this tab's turns", () => {
  it("reloads for a run another channel had going when this tab sent, once it ends after the turn", async () => {
    const c = backend.create({ title: "Sau lượt", messages: [storedMessage("user", "chào")] });
    const release = holdTurns();
    backend.nextTurn = [...webTurn];
    await openConversation("Sau lượt", [run(c.id, "running", "telegram", "tg")]);

    await userEvent.type(screen.getByRole("textbox", { name: vi.composerPlaceholder }), "tin web{Enter}");
    // The server announces this tab's own run while it streams, as the hub does.
    act(() => stream().emit({ type: "run", run: run(c.id, "running", "chat", "web") }));
    c.messages.push(storedMessage("assistant", "Đã nhận"));
    await release();
    await screen.findByText("Đã nhận");
    act(() => stream().emit({ type: "run", run: run(c.id, "done", "chat", "web") }));
    await act(async () => {});
    // The turn is over and the Telegram run is not: the thread says something is going.
    expect(screen.queryByRole("button", { name: vi.stop })).not.toBeInTheDocument();
    expect(screen.getByTestId("thinking")).toBeInTheDocument();

    c.messages.push(storedMessage("assistant", "Trả lời qua Telegram"));
    const before = threadLoads(c.id);
    act(() => stream().emit({ type: "run", run: run(c.id, "done", "telegram", "tg") }));
    expect(await screen.findByText("Trả lời qua Telegram")).toBeInTheDocument();
    expect(threadLoads(c.id)).toBe(before + 1);
  });

  it("still counts a run as going already after the stream came back, when this tab sends", async () => {
    const c = backend.create({ title: "Nối lại", messages: [storedMessage("user", "chào")] });
    const release = holdTurns();
    backend.nextTurn = [...webTurn];
    const telegram = run(c.id, "running", "telegram", "tg");
    await openConversation("Nối lại", [telegram]);
    // The browser's own retry: the snapshot says the Telegram run is still going.
    act(() => stream().onerror?.());
    act(() => {
      stream().open();
      stream().emit({ type: "snapshot", runs: [telegram] });
    });
    await act(async () => {});

    await userEvent.type(screen.getByRole("textbox", { name: vi.composerPlaceholder }), "tin web{Enter}");
    act(() => stream().emit({ type: "run", run: run(c.id, "running", "chat", "web") }));
    c.messages.push(storedMessage("assistant", "Đã nhận"));
    await release();
    await screen.findByText("Đã nhận");
    act(() => stream().emit({ type: "run", run: run(c.id, "done", "chat", "web") }));
    await act(async () => {});

    c.messages.push(storedMessage("assistant", "Trả lời qua Telegram"));
    const before = threadLoads(c.id);
    act(() => stream().emit({ type: "run", run: run(c.id, "done", "telegram", "tg") }));
    expect(await screen.findByText("Trả lời qua Telegram")).toBeInTheDocument();
    expect(threadLoads(c.id)).toBe(before + 1);
  });

  it("loads the reply of a run another channel ended during this tab's turn once the turn is over", async () => {
    const c = backend.create({ title: "Giữa lượt", messages: [storedMessage("user", "chào")] });
    const release = holdTurns();
    backend.nextTurn = [...webTurn];
    await openConversation("Giữa lượt", [run(c.id, "running", "telegram", "tg")]);

    await userEvent.type(screen.getByRole("textbox", { name: vi.composerPlaceholder }), "tin web{Enter}");
    act(() => stream().emit({ type: "run", run: run(c.id, "running", "chat", "web") }));
    c.messages.push(storedMessage("assistant", "Trả lời qua Telegram"));
    const during = threadLoads(c.id);
    act(() => stream().emit({ type: "run", run: run(c.id, "done", "telegram", "tg") }));
    await act(async () => {});
    // A load now would wipe the turn this tab is streaming: it waits for the turn.
    expect(threadLoads(c.id)).toBe(during);
    expect(screen.getByRole("button", { name: vi.stop })).toBeInTheDocument();

    c.messages.push(storedMessage("assistant", "Đã nhận"));
    await release();
    expect(await screen.findByText("Trả lời qua Telegram")).toBeInTheDocument();
    expect(screen.getByText("Đã nhận")).toBeInTheDocument();
    expect(threadLoads(c.id)).toBe(during + 1);
  });

  it("follows the run a decision taken elsewhere resumed, and says the request was handled", async () => {
    const call = { id: "tc", name: "write_file", arguments: { path: "b" } };
    const c = backend.create({
      title: "Duyệt nơi khác",
      status: "awaiting_approval",
      pending_approval: fakeApproval({ status: "pending", resolved_at: null, arguments: { path: "b" } }),
      messages: [storedMessage("user", "ghi b"), storedMessage("assistant", "", { tool_calls: [call] })],
    });
    const release = holdTurns();
    await openConversation("Duyệt nơi khác", [run(c.id, "awaiting_approval")]);
    const bar = await screen.findByRole("alertdialog");

    // Telegram approves first: the request closes and its run resumes under the same id.
    Object.assign(c, { status: "idle", pending_approval: null });
    await userEvent.click(within(bar).getByRole("button", { name: vi.approve }));
    act(() => stream().emit({ type: "run", run: run(c.id, "running") }));
    await release();

    const notice = await screen.findByTestId("notice");
    expect(notice.textContent).toBe(vi.attentionHandled);
    expect(notice).not.toHaveClass("error");
    const card = screen.getByTestId("tool-card");
    expect(card).toHaveTextContent(vi.toolRunning);
    expect(screen.getByTestId("thinking")).toBeInTheDocument();

    c.messages.push(
      storedMessage("tool", "đã ghi", { tool_call_id: "tc", name: "write_file" }),
      storedMessage("assistant", "Đã ghi tệp b qua Telegram."),
    );
    act(() => stream().emit({ type: "run", run: run(c.id, "done") }));
    expect(await screen.findByText("Đã ghi tệp b qua Telegram.")).toBeInTheDocument();
    expect(screen.getByTestId("tool-card")).toHaveTextContent(vi.toolDone);
  });
});

/** Holds the next load of one conversation once armed; its answer is taken on arrival. */
function holdNextLoad(id: string) {
  const load = door();
  let armed = false;
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await backend.fetch(input, init);
    if (armed && !init?.method && String(input).endsWith(`/conversations/${id}`)) {
      armed = false;
      await load.shut;
    }
    return response;
  });
  return { arm: () => (armed = true), open: () => act(async () => load.open()) };
}

describe("answers for the conversation left behind arriving late", () => {
  async function switchToB() {
    await userEvent.click(screen.getByRole("button", { name: /Hội thoại B/ }));
    await screen.findByText("tin của B");
  }

  function expectB() {
    expect(screen.getByRole("heading", { level: 1, name: "Hội thoại B" })).toBeInTheDocument();
    expect(screen.getByText("tin của B")).toBeInTheDocument();
    expect(screen.queryByText("tin của A")).not.toBeInTheDocument();
  }

  it("leaves the conversation opened since alone when it was the first load", async () => {
    const a = backend.create({ title: "Hội thoại A", messages: [storedMessage("user", "tin của A")] });
    backend.create({ title: "Hội thoại B", messages: [storedMessage("user", "tin của B")] });
    const hold = holdNextLoad(a.id);
    hold.arm();
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Hội thoại A/ }));
    await screen.findByRole("heading", { level: 1, name: "Hội thoại A" });

    await switchToB();
    await hold.open();
    expectB();
  });

  it("leaves it alone when the load was for a run that ended there", async () => {
    const a = backend.create({ title: "Hội thoại A", messages: [storedMessage("user", "tin của A")] });
    backend.create({ title: "Hội thoại B", messages: [storedMessage("user", "tin của B")] });
    const hold = holdNextLoad(a.id);
    await openConversation("Hội thoại A", [run(a.id, "running")]);
    await screen.findByText("tin của A");

    a.messages.push(storedMessage("assistant", "Trả lời A qua Telegram"));
    hold.arm();
    act(() => stream().emit({ type: "run", run: run(a.id, "done") }));
    await act(async () => {});
    await switchToB();
    await hold.open();
    expectB();
    expect(screen.queryByText("Trả lời A qua Telegram")).not.toBeInTheDocument();
  });

  it("says nothing there of a decision the conversation left had found taken", async () => {
    const a = backend.create({
      title: "Hội thoại A",
      status: "awaiting_approval",
      pending_approval: fakeApproval({ status: "pending", resolved_at: null }),
      messages: [storedMessage("user", "tin của A"), storedMessage("assistant", "", { tool_calls: [{ id: "tc", name: "write_file", arguments: {} }] })],
    });
    backend.create({ title: "Hội thoại B", messages: [storedMessage("user", "tin của B")] });
    const hold = holdNextLoad(a.id);
    await openConversation("Hội thoại A", [run(a.id, "awaiting_approval")]);
    const bar = await screen.findByRole("alertdialog");

    // Decided on another device meanwhile: the decision here meets a 409 and loads A again.
    Object.assign(a, { status: "idle", pending_approval: null });
    hold.arm();
    await userEvent.click(within(bar).getByRole("button", { name: vi.approve }));
    await switchToB();
    await hold.open();
    expectB();
    expect(screen.queryByTestId("notice")).not.toBeInTheDocument();
  });

  it("keeps a decision refused after the switch from taking this tab's run there for another's", async () => {
    const a = backend.create({
      title: "Hội thoại A",
      status: "awaiting_approval",
      pending_approval: fakeApproval({ status: "pending", resolved_at: null }),
      messages: [storedMessage("user", "tin của A"), storedMessage("assistant", "", { tool_calls: [{ id: "tc", name: "write_file", arguments: {} }] })],
    });
    const b = backend.create({ title: "Hội thoại B", messages: [storedMessage("user", "tin của B")] });
    const release = holdTurns();
    await openConversation("Hội thoại A", [run(a.id, "awaiting_approval")]);
    const bar = await screen.findByRole("alertdialog");

    // Decided on another device meanwhile; the person moves on to B and writes there
    // before the decision taken here hears back.
    Object.assign(a, { status: "idle", pending_approval: null });
    await userEvent.click(within(bar).getByRole("button", { name: vi.approve }));
    await switchToB();
    backend.nextTurn = [...webTurn];
    await userEvent.type(screen.getByRole("textbox", { name: vi.composerPlaceholder }), "tin web{Enter}");
    act(() => stream().emit({ type: "run", run: run(b.id, "running", "chat", "web") }));
    b.messages.push(storedMessage("assistant", "Đã nhận"));
    await release();
    await screen.findByText("Đã nhận");
    // The run is the one this tab streamed: nothing else is going there, nothing to load.
    expect(screen.queryByTestId("thinking")).not.toBeInTheDocument();
    const before = threadLoads(b.id);
    act(() => stream().emit({ type: "run", run: run(b.id, "done", "chat", "web") }));
    await act(async () => {});
    expect(threadLoads(b.id)).toBe(before);
    expectB();
  });
});
