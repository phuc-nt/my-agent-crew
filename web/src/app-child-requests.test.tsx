import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import type { ApprovalInfo, RunInfo } from "./api/types";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, coachAgent, fakeAgent, fakeApproval, fakeRun } from "./test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  backend.agents = [fakeAgent, coachAgent];
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
  document.title = "My Agent Crew";
});

afterEach(() => vitest.unstubAllGlobals());

const inFiveMinutes = () => new Date(Date.now() + 5 * 60_000).toISOString();
const COACH = coachAgent.name;

/** The master's chat, its turn still going on a delegate call, and a child of `delegatedBy`
 *  paused on `approval` in a conversation of its own. */
function delegatedRequest(approval: Partial<ApprovalInfo> = {}, depth = 1) {
  const parent = backend.create({ title: "Lên kế hoạch" });
  const turn = fakeRun({ id: "turn", conversation_id: parent.id, status: "running", finished_at: null });
  let delegatedBy = parent.id;
  const between: RunInfo[] = [];
  for (let level = 1; level < depth; level++) {
    const middle = backend.create({ agent_id: "default", parent_call_id: `d${level}`, title: "Việc giữa" });
    between.push(fakeRun({ id: `middle${level}`, conversation_id: middle.id, source: `delegate:${delegatedBy}`, status: "running", finished_at: null }));
    delegatedBy = middle.id;
  }
  const pending_approval = fakeApproval({ status: "pending", resolved_at: null, expires_at: inFiveMinutes(), ...approval });
  const child = backend.create({ agent_id: "coach", parent_call_id: "d0", status: "awaiting_approval", pending_approval });
  pending_approval.conversation_id = child.id;
  const asking = fakeRun({
    id: "child",
    agent_id: "coach",
    conversation_id: child.id,
    source: `delegate:${delegatedBy}`,
    status: "awaiting_approval",
    finished_at: null,
    steps: approval.kind === "question" ? [{ kind: "question", question: "Dời hạn?", duration_ms: null }] : [],
  });
  backend.runs = [asking, ...between, turn];
  backend.nextTurn = [{ type: "done", spent_usd: 0, unknown_cost_calls: 0 }];
  window.location.hash = `#/chat/${parent.id}`;
  return { parent, child, asking, turn, between };
}

const card = () => screen.findByRole("region", { name: vi.attentionDelegated });

describe("App with a delegated child waiting on the person", () => {
  it("shows the child's request in the parent's chat and settles it there", async () => {
    const { child, asking, turn } = delegatedRequest();
    render(<App />);

    const requests = await card();
    const bar = await within(requests).findByRole("group", { name: new RegExp(`^${vi.attentionAwaiting(COACH)}`) });
    // The parent's own composer is not blocked: only the child is waiting.
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();

    backend.runs = [{ ...asking, status: "done", finished_at: "2026-09-19T08:01:00Z" }, turn];
    await userEvent.click(within(bar).getByRole("button", { name: vi.approve }));

    expect(backend.requests.some((r) => r.method === "POST" && r.path === `/conversations/${child.id}/approvals/ap1`)).toBe(true);
    await waitFor(() => expect(screen.queryByRole("region", { name: vi.attentionDelegated })).not.toBeInTheDocument());
    expect(window.location.hash).toBe(`#/chat/${turn.conversation_id}`);
  });

  it("answers a grandchild's question from the root's chat, naming the child it works for", async () => {
    const question = { id: "aq1", kind: "question" as const, tool_name: "ask_user", arguments: { question: "Dời hạn?" }, options: ["Thứ sáu", "Thứ hai"] };
    const { child } = delegatedRequest(question, 2);
    render(<App />);

    const requests = await card();
    const asked = await within(requests).findByRole("group", { name: new RegExp(`^${vi.attentionAsking(COACH)}`) });
    expect(within(requests).getByTestId("attention-child")).toHaveTextContent(vi.delegateChildOf.replace("{parent}", "Việc"));
    await userEvent.click(within(asked).getByRole("button", { name: "Thứ sáu" }));

    expect(backend.requests.some((r) => r.method === "POST" && r.path === `/conversations/${child.id}/approvals/aq1/answer`)).toBe(true);
    expect(backend.lastAnswer).toBe("Thứ sáu");
  });

  it("opens the child's conversation from its row", async () => {
    const { child } = delegatedRequest();
    render(<App />);

    await userEvent.click(within(await card()).getByRole("button", { name: vi.openConversation }));
    await waitFor(() => expect(window.location.hash).toBe(`#/chat/${child.id}`));
  });

  // Another conversation's delegated work is counted, but not decided from this chat.
  it("keeps another conversation's child out of this chat and counts it on the way to Duyệt", async () => {
    delegatedRequest();
    const other = backend.create({ title: "Khác" });
    window.location.hash = `#/chat/${other.id}`;
    render(<App />);

    await waitFor(() => expect(screen.getByTestId("manage-waiting")).toHaveTextContent(`1 ${vi.manage.waitingBadge}`));
    expect(screen.queryByRole("region", { name: vi.attentionDelegated })).not.toBeInTheDocument();
  });

  // A decision holds work up until it is taken; a failure only waits to be read.
  it("counts waiting requests apart from unread failures on the way out of the chat", async () => {
    const { asking, turn } = delegatedRequest();
    backend.runs = [asking, turn, fakeRun({ id: "broke", status: "error" }), fakeRun({ id: "cut", status: "halted" })];
    render(<App />);

    const manage = await screen.findByRole("button", { name: /Quản lý/ });
    await waitFor(() => expect(within(manage).getByTestId("manage-waiting")).toHaveTextContent(`1 ${vi.manage.waitingBadge}`));
    expect(manage.querySelector(".badge.danger")).toHaveTextContent(`2 ${vi.manage.failedBadge}`);
    await userEvent.click(manage);
    await waitFor(() => expect(window.location.hash).toBe("#/manage/approvals"));
  });

  it("appears as soon as the activity stream says a child paused", async () => {
    const { asking } = delegatedRequest();
    backend.runs = [];
    render(<App />);
    await screen.findByRole("button", { name: /Quản lý/ });
    expect(screen.queryByRole("region", { name: vi.attentionDelegated })).not.toBeInTheDocument();

    const stream = FakeEventSource.instances.at(-1)!;
    act(() => {
      stream.open();
      stream.emit({ type: "snapshot", runs: [asking] });
    });
    expect(await card()).toBeInTheDocument();
  });
});
