import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
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

  it("lands on the activity page when nothing waits on a decision", async () => {
    backend.runs = [fakeRun({ id: "broke", status: "error" })];
    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: /Quản lý/ })).toHaveTextContent("1"));

    await userEvent.click(screen.getByRole("button", { name: /Quản lý/ }));

    await waitFor(() => expect(window.location.hash).toBe("#/manage/activity"));
    expect(document.title).toBe("My Agent Crew");
  });
});
