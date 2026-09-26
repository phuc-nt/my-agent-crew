import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { ApprovalInfo, RunInfo } from "../api/types";
import { vi } from "../i18n/vi";
import { FakeBackend, fakeApproval, fakeRun } from "../test/fake-backend";
import { AttentionCenter } from "./attention-center";

const name = () => "Agent";
let backend: FakeBackend;
/** The approval routes whose resumed stream was read to its very end. */
let drained: string[];
/** Until it settles, a decide or answer stream stays open, as a turn still running does. */
let turnEnds: Promise<void>;

beforeEach(() => {
  backend = new FakeBackend();
  drained = [];
  turnEnds = Promise.resolve();
  vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await backend.fetch(input, init);
    if (!String(input).includes("/approvals/") || !response.ok || !response.body) return response;
    const reader = response.body.getReader();
    const body = new ReadableStream<Uint8Array>({
      async pull(controller) {
        const { done, value } = await reader.read();
        if (!done) return controller.enqueue(value);
        await turnEnds;
        drained.push(new URL(String(input), "http://fake").pathname.replace(/^\/api/, ""));
        controller.close();
      },
    });
    return new Response(body, { status: response.status, headers: response.headers });
  });
});

afterEach(() => {
  vitest.useRealTimers();
  vitest.unstubAllGlobals();
});

const inFiveMinutes = () => new Date(Date.now() + 5 * 60_000).toISOString();

/** A conversation paused on `approval`, and the run the activity list shows for it. */
function waiting(approval: Partial<ApprovalInfo> = {}) {
  const pending_approval = fakeApproval({ status: "pending", resolved_at: null, expires_at: inFiveMinutes(), arguments: { path: "notes.md" }, ...approval });
  const conversation = backend.create({ status: "awaiting_approval", pending_approval });
  backend.nextTurn = [{ type: "done", spent_usd: 0, unknown_cost_calls: 0 }];
  const run = fakeRun({ id: `run-${conversation.id}`, status: "awaiting_approval", finished_at: null, conversation_id: conversation.id });
  return { conversation, run };
}

function inline(runs: RunInfo[], onReload = vitest.fn()) {
  render(<AttentionCenter runs={runs} inline agentName={name} onOpenConversation={() => undefined} onReload={onReload} />);
  return onReload;
}

describe("AttentionCenter with requests settled in place", () => {
  it("decides a waiting tool call where it is listed and lets the row go once the turn ends", async () => {
    const { conversation, run } = waiting();
    let endTurn = () => {};
    turnEnds = new Promise((resolve) => (endTurn = resolve));
    const onReload = inline([run]);

    const bar = await screen.findByRole("alertdialog", { name: vi.awaitingApproval });
    expect(bar).toHaveTextContent(vi.approvalTitle("write_file"));
    expect(bar).toHaveTextContent("path=notes.md");
    expect(within(bar).getByRole("timer")).toHaveTextContent(/^còn \d:\d\d$/);
    await userEvent.click(within(bar).getByRole("button", { name: vi.approve }));

    // The server has the decision, but the turn it resumed is still running: the row stays.
    expect(await screen.findByText(vi.attentionResuming)).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(screen.getByTestId("attention-row")).toBeInTheDocument();
    endTurn();

    await waitFor(() => expect(screen.queryByTestId("attention-row")).not.toBeInTheDocument());
    const path = `/conversations/${conversation.id}/approvals/ap1`;
    expect(backend.requests.find((r) => r.method === "POST")).toEqual({ method: "POST", path, body: { approve: true } });
    expect(drained).toEqual([path]);
    expect(onReload).toHaveBeenCalled();
    expect(screen.getByText(vi.attentionEmpty)).toBeInTheDocument();
  });

  it("answers a waiting question with one of its choices and lets the row go", async () => {
    const { conversation, run } = waiting({ id: "aq1", kind: "question", tool_name: "ask_user", arguments: { question: "Dời hạn?" }, options: ["Thứ sáu", "Thứ hai"] });
    inline([run]);

    const card = await screen.findByRole("alertdialog", { name: vi.awaitingAnswer });
    expect(card).toHaveTextContent("Dời hạn?");
    await userEvent.click(within(card).getByRole("button", { name: "Thứ sáu" }));

    await waitFor(() => expect(screen.queryByTestId("attention-row")).not.toBeInTheDocument());
    const path = `/conversations/${conversation.id}/approvals/aq1/answer`;
    expect(backend.requests.find((r) => r.method === "POST")).toMatchObject({ path, body: { answer: "Thứ sáu" } });
    expect(drained).toEqual([path]);
  });

  // A resumed turn can stop on its next tool: the same run still waits, so the row stays.
  it("keeps the row and shows the next request when the resumed turn pauses again", async () => {
    const { run } = waiting();
    backend.nextTurn = [{ type: "approval_required", approval_id: "ap2", tool_call_id: "tc2", name: "shell_run", arguments: { command: "make" }, reason: "", expires_at: inFiveMinutes() }];
    inline([run]);
    await userEvent.click(await screen.findByRole("button", { name: vi.approve }));

    expect(await screen.findByText(vi.approvalTitle("shell_run"))).toBeInTheDocument();
    expect(screen.getByTestId("attention-row")).toHaveTextContent("command=make");
    expect(screen.getByRole("button", { name: vi.approve })).toBeEnabled();
  });

  // Another tab, Telegram or the expiry sweep can close the request first. The 409 must read
  // as "already handled", not as the chat's "busy", which would send the person to wait.
  it.each([
    ["decide", {}, vi.approve],
    ["answer", { kind: "question" as const, arguments: { question: "Dời hạn?" }, options: ["Thứ sáu"] }, "Thứ sáu"],
  ])("says a request closed elsewhere was handled when a %s meets a 409, and reloads", async (_, approval, button) => {
    const { conversation, run } = waiting(approval);
    const onReload = inline([run]);
    const card = await screen.findByRole("alertdialog");
    backend.conversations.get(conversation.id)!.pending_approval = null;

    await userEvent.click(within(card).getByRole("button", { name: button }));

    expect(await screen.findByText(vi.attentionHandled)).toBeInTheDocument();
    expect(screen.queryByText(vi.busyConflict)).not.toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(onReload).toHaveBeenCalled();
    expect(drained).toEqual([]);
  });

  it("counts down to the deadline, then disables the buttons, says it expired and reloads", async () => {
    vitest.useFakeTimers({ shouldAdvanceTime: true });
    vitest.setSystemTime(new Date("2026-09-26T10:00:00Z"));
    const { run } = waiting({ expires_at: "2026-09-26T10:01:05Z" });
    const onReload = inline([run]);

    const bar = await screen.findByRole("alertdialog");
    expect(within(bar).getByRole("timer")).toHaveTextContent(/^còn 1:0\d$/);
    expect(within(bar).getByRole("button", { name: vi.approve })).toBeEnabled();
    expect(onReload).not.toHaveBeenCalled();

    act(() => vitest.advanceTimersByTime(66_000));

    expect(within(bar).getByRole("timer")).toHaveTextContent(vi.attentionExpired);
    expect(within(bar).getByRole("button", { name: vi.approve })).toBeDisabled();
    expect(within(bar).getByRole("button", { name: vi.deny })).toBeDisabled();
    expect(onReload).toHaveBeenCalledTimes(1);
  });
});
