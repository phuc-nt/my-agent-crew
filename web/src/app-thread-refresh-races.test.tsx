import { act, render, screen } from "@testing-library/react";
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

function run(conversationId: string, status: RunInfo["status"], source = "telegram"): RunInfo {
  const live = status === "running" || status === "awaiting_approval";
  return fakeRun({ id: "r1", conversation_id: conversationId, source, status, finished_at: live ? null : "2026-09-19T08:00:05Z" });
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
