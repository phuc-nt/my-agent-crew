import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { ActivityPayload, RunInfo } from "./api/types";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, fakeApproval, fakeRun } from "./test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
  window.location.hash = "";
  document.title = "My Agent Crew";
});

afterEach(() => vitest.unstubAllGlobals());

/** A conversation paused on a tool request, and its run waiting in the activity list. */
function waitingConversation() {
  const expires = new Date(Date.now() + 5 * 60_000).toISOString();
  const pending_approval = fakeApproval({ status: "pending", resolved_at: null, expires_at: expires });
  const c = backend.create({ status: "awaiting_approval", pending_approval });
  const waitingRun = fakeRun({ id: "w", status: "awaiting_approval", finished_at: null, conversation_id: c.id });
  backend.runs = [waitingRun];
  return { c, waitingRun, expires };
}

/** Lands on the approvals page, where the ledger of settled requests is still empty. */
async function openLedger() {
  render(<App />);
  await waitFor(() => expect(document.title).toBe("(1) My Agent Crew"));
  await userEvent.click(screen.getByRole("button", { name: /Quản lý/ }));
  expect(await screen.findByText(vi.approvalHistoryEmpty)).toBeInTheDocument();
}

describe("App requests waiting on the person", () => {
  // The loop this exists for: a run waits, the tab says so from the background, one click
  // lands where it is decided, and deciding it clears every count without opening the chat.
  it("counts a waiting request in the title, lands on it and settles it in place", async () => {
    const expires = new Date(Date.now() + 5 * 60_000).toISOString();
    const pending_approval = fakeApproval({ status: "pending", resolved_at: null, expires_at: expires });
    const c = backend.create({ title: "Chờ duyệt", status: "awaiting_approval", pending_approval });
    const waitingRun = fakeRun({ id: "w", status: "awaiting_approval", finished_at: null, conversation_id: c.id });
    backend.runs = [waitingRun];
    render(<App />);

    await waitFor(() => expect(document.title).toBe("(1) My Agent Crew"));
    await userEvent.click(screen.getByRole("button", { name: /Quản lý/ }));
    await waitFor(() => expect(window.location.hash).toBe("#/manage/approvals"));

    const attention = screen.getByTestId("attention");
    const bar = await within(attention).findByRole("group", { name: new RegExp(`^${vi.attentionAwaiting("Agent")}`) });
    // What the server reports once the resumed turn is over.
    backend.nextTurn = [{ type: "done", spent_usd: 0, unknown_cost_calls: 0 }];
    backend.runs = [{ ...waitingRun, status: "done", finished_at: "2026-09-19T08:01:00Z" }];
    await userEvent.click(within(bar).getByRole("button", { name: vi.approve }));

    await waitFor(() => expect(document.title).toBe("My Agent Crew"));
    expect(within(attention).queryByTestId("attention-row")).not.toBeInTheDocument();
    expect(backend.requests.some((r) => r.method === "POST" && r.path === `/conversations/${c.id}/approvals/ap1`)).toBe(true);
    expect(window.location.hash).toBe("#/manage/approvals");
    expect(screen.getByRole("button", { name: vi.approvalsTab })).toBeInTheDocument();
  });

  // The server flips a run back to running the moment a decision reaches it, so the run
  // leaves the waiting list while its turn is still going. The row it was decided in has to
  // stay, say the run is resuming, and take the next request if the turn pauses again.
  it("keeps a decided row in place while its run resumes, and shows the next request there", async () => {
    const expires = new Date(Date.now() + 5 * 60_000).toISOString();
    const pending_approval = fakeApproval({ status: "pending", resolved_at: null, expires_at: expires });
    const c = backend.create({ status: "awaiting_approval", pending_approval });
    const waitingRun = fakeRun({ id: "w", status: "awaiting_approval", finished_at: null, conversation_id: c.id });
    backend.runs = [waitingRun];
    let endTurn = () => {};
    const turnEnds = new Promise<void>((resolve) => (endTurn = resolve));
    // The decide stream stays open until the resumed turn ends, as the server's does.
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      const response = await backend.fetch(input, init);
      if (!String(input).includes("/approvals/") || !response.body) return response;
      const reader = response.body.getReader();
      const body = new ReadableStream<Uint8Array>({
        async pull(controller) {
          const { done, value } = await reader.read();
          if (!done) return controller.enqueue(value);
          await turnEnds;
          controller.close();
        },
      });
      return new Response(body, { status: response.status, headers: response.headers });
    });
    render(<App />);
    await waitFor(() => expect(document.title).toBe("(1) My Agent Crew"));
    await userEvent.click(screen.getByRole("button", { name: /Quản lý/ }));

    const row = await screen.findByTestId("attention-row");
    backend.nextTurn = [{ type: "approval_required", approval_id: "ap2", tool_call_id: "tc2", name: "shell_run", arguments: { command: "make" }, reason: "", expires_at: expires }];
    await userEvent.click(await within(row).findByRole("button", { name: vi.approve }));
    const stream = FakeEventSource.instances.at(-1)!;
    act(() => stream.emit({ type: "run", run: { ...waitingRun, status: "running" } }));

    expect(await within(row).findByText(vi.attentionResuming)).toBeInTheDocument();
    expect(screen.getByTestId("attention-row")).toBe(row);

    // The turn stops on its next tool: the same run waits again, in the same row.
    act(() => stream.emit({ type: "run", run: waitingRun }));
    endTurn();
    expect(await within(row).findByText(vi.approvalTitle("shell_run"))).toBeInTheDocument();
    expect(screen.getByTestId("attention-row")).toBe(row);
    expect(within(row).getByRole("button", { name: vi.approve })).toBeEnabled();
    expect(within(row).queryByText(vi.attentionResuming)).not.toBeInTheDocument();
  });

  // A request settles as its run leaves the pause, and the page hears of that in whatever
  // shape the news takes. A resume with nothing slow in it arrives as the run already over:
  // one update in which a run stops waiting and a run ends. A pause that went by while the
  // stream was down arrives as a run that ended, never seen waiting.
  it.each([
    ["as soon as its run goes on", (w: RunInfo): RunInfo => ({ ...w, status: "running" })],
    ["when its run is next seen already finished", (w: RunInfo): RunInfo => ({ ...w, status: "done", finished_at: "2026-09-19T08:01:00Z" })],
    ["when it went by unseen and its run is heard of finished", (): RunInfo => fakeRun({ id: "x", conversation_id: "c-x" })],
  ])("lists a request settled elsewhere %s", async (_, news) => {
    const { waitingRun } = waitingConversation();
    await openLedger();

    const run = news(waitingRun);
    backend.approvals = [fakeApproval({ conversation_id: run.conversation_id ?? "" })];
    act(() => FakeEventSource.instances.at(-1)!.emit({ type: "run", run }));

    const history = await screen.findByTestId("approval-history");
    expect(within(history).getAllByRole("listitem")).toHaveLength(1);
  });

  // The request's run goes on in the same update in which another conversation's run starts
  // waiting: a reconnect's snapshot, or two runs heard of at once. Nothing has finished and
  // one run still waits, so only which run waits says a request has settled.
  it.each([
    ["in one snapshot", (resumed: RunInfo, next: RunInfo): ActivityPayload[] => [{ type: "snapshot", runs: [resumed, next] }]],
    ["in two runs heard of at once", (resumed: RunInfo, next: RunInfo): ActivityPayload[] => [{ type: "run", run: resumed }, { type: "run", run: next }]],
  ])("lists a request settled elsewhere as another run starts waiting, %s", async (_, news) => {
    const { c, waitingRun, expires } = waitingConversation();
    const pending_approval = fakeApproval({ id: "ap9", status: "pending", resolved_at: null, expires_at: expires });
    const d = backend.create({ status: "awaiting_approval", pending_approval });
    await openLedger();

    const resumed: RunInfo = { ...waitingRun, status: "running" };
    const next = fakeRun({ id: "v", status: "awaiting_approval", finished_at: null, conversation_id: d.id });
    backend.runs = [resumed, next];
    backend.approvals = [fakeApproval({ conversation_id: c.id })];
    const stream = FakeEventSource.instances.at(-1)!;
    act(() => news(resumed, next).forEach((payload) => stream.emit(payload)));

    const history = await screen.findByTestId("approval-history");
    expect(within(history).getAllByRole("listitem")).toHaveLength(1);
    expect(document.title).toBe("(1) My Agent Crew");
  });

  // Deciding in a row settles its request even when the resumed turn stops on its next tool
  // at once: the same run waits again, and the list of runs reads as it did before.
  it("reads the history again after a decision made here, though the run waits again", async () => {
    const { c, expires } = waitingConversation();
    await openLedger();
    const row = await screen.findByTestId("attention-row");

    // What the server holds once the decision reaches it: the request in the ledger, and
    // the turn paused again on its next tool.
    backend.approvals = [fakeApproval({ conversation_id: c.id })];
    backend.nextTurn = [{ type: "approval_required", approval_id: "ap2", tool_call_id: "tc2", name: "shell_run", arguments: { command: "make" }, reason: "", expires_at: expires }];
    await userEvent.click(await within(row).findByRole("button", { name: vi.approve }));

    expect(await within(row).findByText(vi.approvalTitle("shell_run"))).toBeInTheDocument();
    const history = await screen.findByTestId("approval-history");
    expect(within(history).getAllByRole("listitem")).toHaveLength(1);
  });

  it("lands on the activity page when nothing waits on a decision", async () => {
    backend.runs = [fakeRun({ id: "broke", status: "error" })];
    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Quản lý/ })).toHaveTextContent("1"));

    await userEvent.click(screen.getByRole("button", { name: /Quản lý/ }));

    await waitFor(() => expect(window.location.hash).toBe("#/manage/activity"));
    expect(document.title).toBe("My Agent Crew");
  });
});
