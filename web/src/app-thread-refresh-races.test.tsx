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
