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

/** A request in the list is a group named by its row's head, not a page-wide alert. */
const request = () => screen.findByRole("group", { name: new RegExp(`^${vi.attentionAwaiting("Agent")}`) });

function inline(runs: RunInfo[], onReload = vitest.fn()) {
  render(<AttentionCenter runs={runs} inline agentName={name} onOpenConversation={() => undefined} onReload={onReload} />);
  return onReload;
}

describe("AttentionCenter with requests settled in place", () => {
  // Unattended runs are the ones decided here rather than in a chat that streamed the pause,
  // so the row has only the stored request to say why an autonomous run stopped.
  it("says which ask pattern stopped a command", async () => {
    const reason = "khớp mẫu cần duyệt: `rm -rf`";
    const { run } = waiting({ tool_name: "shell_run", arguments: { command: "rm -rf build" }, reason });
    inline([run]);

    const bar = await request();
    expect(bar).toHaveTextContent("command=rm -rf build");
    expect(bar).toHaveTextContent(reason);
  });

  it("decides a waiting tool call where it is listed and lets the row go once the turn ends", async () => {
    const { conversation, run } = waiting();
    let endTurn = () => {};
    turnEnds = new Promise((resolve) => (endTurn = resolve));
    const onReload = inline([run]);

    const bar = await request();
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

  // Requests handed out together start in one second, and start times are whole seconds. A
  // row held while its turn resumes stays where it was listed: the other request's buttons
  // must not slide under the pointer that just decided.
  it.each([
    ["first", 0],
    ["second", 1],
  ])("keeps the %s of two requests of one second where it was listed while its turn resumes", async (_, at) => {
    const pair = [waiting(), waiting({ tool_name: "shell_run", arguments: { command: "make" } })].map((w) => w.run);
    let endTurn = () => {};
    turnEnds = new Promise((resolve) => (endTurn = resolve));
    const center = (runs: RunInfo[]) => (
      <AttentionCenter runs={runs} inline agentName={name} onOpenConversation={() => undefined} onReload={() => undefined} />
    );
    const rows = () =>
      [...screen.getByTestId("attention").querySelectorAll(".attention-list > li .attention-title")].map(
        (title) => pair.find((run) => title.id.endsWith(run.id))?.id,
      );
    const { rerender } = render(center(pair));
    await waitFor(() => expect(screen.getAllByRole("group")).toHaveLength(2));
    const groups = screen.getAllByRole("group", { name: new RegExp(`^${vi.attentionAwaiting("Agent")}`) });
    expect(rows()).toEqual(["run-c1", "run-c2"]);

    await userEvent.click(within(groups[at]).getByRole("button", { name: vi.approve }));
    expect(await screen.findByText(vi.attentionResuming)).toBeInTheDocument();
    // The run waits no more, so the activity list leaves it out.
    rerender(center(pair.filter((_, i) => i !== at)));

    expect(rows()).toEqual(["run-c1", "run-c2"]);
    endTurn();
    await waitFor(() => expect(rows()).toEqual([pair[1 - at].id]));
  });

  it("answers a waiting question with one of its choices and lets the row go", async () => {
    const { conversation, run } = waiting({ id: "aq1", kind: "question", tool_name: "ask_user", arguments: { question: "Dời hạn?" }, options: ["Thứ sáu", "Thứ hai"] });
    inline([run]);

    const card = await request();
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

  // The server takes the decision and resumes the run, then the stream carrying the turn is
  // cut. The request shown is over, so its buttons must go; the error stays until it is read.
  it("keeps a row whose resumed stream broke, with the error and no stale buttons, until read", async () => {
    const { run } = waiting();
    vitest.stubGlobal("fetch", async (input: RequestInfo | URL, init?: RequestInit) => {
      const response = await backend.fetch(input, init);
      if (!String(input).includes("/approvals/")) return response;
      const cut = new ReadableStream<Uint8Array>({ pull: (controller) => controller.error(new TypeError("network error")) });
      return new Response(cut, { status: 200, headers: response.headers });
    });
    inline([run]);
    await userEvent.click(within(await request()).getByRole("button", { name: vi.approve }));

    expect(await screen.findByText(vi.errorPrefix + "network error")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("group")).not.toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: vi.attentionSeenLabel(vi.attentionAwaiting("Agent")) }));
    expect(screen.queryByTestId("attention-row")).not.toBeInTheDocument();
  });

  // Two requests on one page are two groups, each named by who asks: two identical alerts
  // would leave a screen reader with two "Cho phép" buttons nobody can tell apart.
  it("names each waiting request by its own row instead of one shared alert", async () => {
    const first = waiting();
    const second = waiting({ tool_name: "shell_run", arguments: { command: "make" } });
    const runs = [
      { ...first.run, agent_id: "mai" },
      { ...second.run, agent_id: "lan" },
    ];
    const names = (id: string) => (id === "mai" ? "Mai" : "Lan");
    render(<AttentionCenter runs={runs} inline agentName={names} onOpenConversation={() => undefined} />);

    await waitFor(() => expect(screen.getAllByRole("group")).toHaveLength(2));
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    const mai = screen.getByRole("group", { name: new RegExp(`^${vi.attentionAwaiting("Mai")}`) });
    const lan = screen.getByRole("group", { name: new RegExp(`^${vi.attentionAwaiting("Lan")}`) });
    expect(mai).toHaveTextContent(vi.approvalTitle("write_file"));
    expect(lan).toHaveTextContent(vi.approvalTitle("shell_run"));
  });

  // Deciding from the keyboard must not drop focus to the top of the page when the row
  // leaves: it goes on to the next request, and to the section's heading once none is left.
  it("moves focus to the next request when a row decided from the keyboard leaves", async () => {
    const first = waiting();
    const second = waiting({ tool_name: "shell_run", arguments: { command: "make" } });
    const runs = [
      { ...first.run, agent_id: "mai" },
      { ...second.run, agent_id: "lan" },
    ];
    const names = (id: string) => (id === "mai" ? "Mai" : "Lan");
    render(<AttentionCenter runs={runs} inline agentName={names} onOpenConversation={() => undefined} />);
    const mai = await screen.findByRole("group", { name: new RegExp(`^${vi.attentionAwaiting("Mai")}`) });
    await screen.findByRole("group", { name: new RegExp(`^${vi.attentionAwaiting("Lan")}`) });

    within(mai).getByRole("button", { name: vi.approve }).focus();
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(screen.getAllByTestId("attention-row")).toHaveLength(1));
    const next = screen.getByTestId("attention-row");
    expect(next).toHaveTextContent(vi.attentionAwaiting("Lan"));
    await waitFor(() => expect(next).toContainElement(document.activeElement as HTMLElement));

    within(next).getByRole("button", { name: vi.approve }).focus();
    await userEvent.keyboard("{Enter}");
    await waitFor(() => expect(screen.queryByTestId("attention-row")).not.toBeInTheDocument());
    expect(screen.getByRole("heading", { name: vi.attention })).toHaveFocus();
  });

  // Another tab, Telegram or the expiry sweep can close the request first. The 409 must read
  // as "already handled", not as the chat's "busy", which would send the person to wait.
  it.each([
    ["decide", {}, vi.approve],
    ["answer", { kind: "question" as const, arguments: { question: "Dời hạn?" }, options: ["Thứ sáu"] }, "Thứ sáu"],
  ])("says a request closed elsewhere was handled when a %s meets a 409, and reloads", async (_, approval, button) => {
    const { conversation, run } = waiting(approval);
    const onReload = inline([run]);
    const card = await request();
    backend.conversations.get(conversation.id)!.pending_approval = null;

    await userEvent.click(within(card).getByRole("button", { name: button }));

    expect(await screen.findByText(vi.attentionHandled)).toBeInTheDocument();
    expect(screen.queryByText(vi.busyConflict)).not.toBeInTheDocument();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
    expect(onReload).toHaveBeenCalled();
    expect(drained).toEqual([]);
  });

  // The request was closed first, but the turn that resumed has already paused on the next
  // one. That new request is open: it must not read as "already handled".
  it("does not call a newer request handled when a 409's re-read finds one", async () => {
    const { conversation, run } = waiting();
    inline([run]);
    const bar = await request();
    const next = { id: "ap2", conversation_id: conversation.id, tool_name: "shell_run", arguments: { command: "make" } };
    backend.conversations.get(conversation.id)!.pending_approval = fakeApproval({ ...next, status: "pending", resolved_at: null, expires_at: inFiveMinutes() });

    await userEvent.click(within(bar).getByRole("button", { name: vi.approve }));

    expect(await screen.findByText(vi.approvalTitle("shell_run"))).toBeInTheDocument();
    await waitFor(() => expect(within(screen.getByRole("group")).getByRole("button", { name: vi.approve })).toBeEnabled());
    expect(screen.getByRole("group")).toHaveTextContent("command=make");
    expect(screen.queryByText(vi.attentionHandled)).not.toBeInTheDocument();
  });

  // A request whose first read failed is not lost: the row offers to read it again, and
  // reads it on its own when the activity stream hands over the run again.
  it("reads a request again after its first read failed, from its button or a new copy of the run", async () => {
    const { conversation, run } = waiting();
    const through = globalThis.fetch;
    let failures = 2;
    vitest.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) =>
      String(input).endsWith(`/conversations/${conversation.id}`) && failures-- > 0
        ? Promise.reject(new TypeError("offline"))
        : through(input, init),
    );
    const { rerender } = render(
      <AttentionCenter runs={[run]} inline agentName={name} onOpenConversation={() => undefined} />,
    );

    expect(await screen.findByText(vi.errorPrefix + "offline")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: vi.retry }));
    expect(await screen.findByText(vi.errorPrefix + "offline")).toBeInTheDocument();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: vi.retry }));
    expect(within(await request()).getByRole("button", { name: vi.approve })).toBeEnabled();
    expect(screen.queryByRole("button", { name: vi.retry })).not.toBeInTheDocument();

    // The same run again from the stream, now waiting on a newer request.
    backend.conversations.get(conversation.id)!.pending_approval = fakeApproval({ id: "ap2", conversation_id: conversation.id, tool_name: "shell_run", arguments: { command: "make" }, status: "pending", resolved_at: null, expires_at: inFiveMinutes() });
    rerender(<AttentionCenter runs={[{ ...run }]} inline agentName={name} onOpenConversation={() => undefined} />);
    expect(await screen.findByText(vi.approvalTitle("shell_run"))).toBeInTheDocument();
  });

  it("counts down to the deadline, then disables the buttons, says it expired and reloads", async () => {
    vitest.useFakeTimers({ shouldAdvanceTime: true });
    vitest.setSystemTime(new Date("2026-09-26T10:00:00Z"));
    const { run } = waiting({ expires_at: "2026-09-26T10:01:05Z" });
    const onReload = inline([run]);

    const bar = await request();
    expect(within(bar).getByRole("timer")).toHaveTextContent(/^còn 1:0\d$/);
    expect(within(bar).getByRole("button", { name: vi.approve })).toBeEnabled();
    expect(onReload).not.toHaveBeenCalled();

    // The clock starts once the request has loaded, in an effect React may flush on a later
    // task than the one that painted the row: advance, then wait for the row to catch up.
    await act(async () => {
      await vitest.advanceTimersByTimeAsync(66_000);
    });

    await waitFor(() => expect(within(bar).getByRole("timer")).toHaveTextContent(vi.attentionExpired));
    expect(within(bar).getByRole("button", { name: vi.approve })).toBeDisabled();
    expect(within(bar).getByRole("button", { name: vi.deny })).toBeDisabled();
    await waitFor(() => expect(onReload).toHaveBeenCalledTimes(1));
  });

  // The deadline passes before the server's sweep closes the request, so the read made then
  // still finds it open. Once the sweep has run the row reads again and stops waiting.
  it("reads the request and the list again once the expiry sweep has run", async () => {
    vitest.useFakeTimers({ shouldAdvanceTime: true });
    vitest.setSystemTime(new Date("2026-09-26T10:00:00Z"));
    const { conversation, run } = waiting({ expires_at: "2026-09-26T10:00:05Z" });
    const onReload = inline([run]);
    const bar = await request();

    await act(async () => {
      await vitest.advanceTimersByTimeAsync(6_000);
    });
    await waitFor(() => expect(onReload).toHaveBeenCalledTimes(1));
    expect(within(bar).getByRole("timer")).toHaveTextContent(vi.attentionExpired);

    backend.conversations.get(conversation.id)!.pending_approval = null;
    await act(async () => {
      await vitest.advanceTimersByTimeAsync(25_000);
    });

    expect(await screen.findByText(vi.attentionHandled)).toBeInTheDocument();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
    await waitFor(() => expect(onReload).toHaveBeenCalledTimes(2));
  });

  // A job due on the same tick, or a turn resumed by an earlier close, holds the sweep back
  // for minutes. The row keeps reading until it has closed the request, and reads the list
  // again only then: nothing in it has changed while the request is still open.
  it("keeps reading an expired request until a late sweep closes it", async () => {
    vitest.useFakeTimers({ shouldAdvanceTime: true });
    vitest.setSystemTime(new Date("2026-09-26T10:00:00Z"));
    const { conversation, run } = waiting({ expires_at: "2026-09-26T10:00:05Z" });
    const onReload = inline([run]);
    const bar = await request();

    await act(async () => {
      await vitest.advanceTimersByTimeAsync(6_000);
    });
    await waitFor(() => expect(onReload).toHaveBeenCalledTimes(1));

    await act(async () => {
      await vitest.advanceTimersByTimeAsync(75_000);
    });
    expect(within(bar).getByRole("timer")).toHaveTextContent(vi.attentionExpired);
    expect(within(bar).getByRole("button", { name: vi.approve })).toBeDisabled();
    expect(onReload).toHaveBeenCalledTimes(1);

    backend.conversations.get(conversation.id)!.pending_approval = null;
    await act(async () => {
      await vitest.advanceTimersByTimeAsync(25_000);
    });

    expect(await screen.findByText(vi.attentionHandled)).toBeInTheDocument();
    expect(screen.queryByRole("group")).not.toBeInTheDocument();
    await waitFor(() => expect(onReload).toHaveBeenCalledTimes(2));
  });

  // Offline, a read that fails says nothing about the request: the list is read again once a
  // read sees the request closed, not after every poll that could not look.
  it("does not read the list again while an expired request cannot be read", async () => {
    vitest.useFakeTimers({ shouldAdvanceTime: true });
    vitest.setSystemTime(new Date("2026-09-26T10:00:00Z"));
    const { conversation, run } = waiting({ expires_at: "2026-09-26T10:00:05Z" });
    const onReload = inline([run]);
    const bar = await request();

    await act(async () => {
      await vitest.advanceTimersByTimeAsync(6_000);
    });
    await waitFor(() => expect(onReload).toHaveBeenCalledTimes(1));

    const reachable = globalThis.fetch;
    let offline = true;
    let unread = 0;
    vitest.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) => {
      if (!offline || !String(input).endsWith(`/conversations/${conversation.id}`)) return reachable(input, init);
      unread += 1;
      return Promise.reject(new TypeError("offline"));
    });
    await act(async () => {
      await vitest.advanceTimersByTimeAsync(75_000);
    });
    expect(unread).toBe(3);
    expect(within(bar).getByRole("timer")).toHaveTextContent(vi.attentionExpired);
    expect(within(bar).getByRole("button", { name: vi.approve })).toBeDisabled();
    expect(onReload).toHaveBeenCalledTimes(1);

    offline = false;
    backend.conversations.get(conversation.id)!.pending_approval = null;
    await act(async () => {
      await vitest.advanceTimersByTimeAsync(25_000);
    });

    expect(await screen.findByText(vi.attentionHandled)).toBeInTheDocument();
    await waitFor(() => expect(onReload).toHaveBeenCalledTimes(2));
  });
});
