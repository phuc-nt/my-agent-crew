import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { afterEach, beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, coachAgent, fakeAgent, fakeRun, listItem, storedMessage } from "./test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
  // The app reads its screen from the address bar, and jsdom keeps one address for the
  // whole file — so without this each test would start wherever the last one navigated.
  window.location.hash = "";
});

// A test that widens the screen must not leave the rest of the file wide.
afterEach(() => vitest.unstubAllGlobals());

function stream(): FakeEventSource {
  const source = FakeEventSource.instances.at(-1);
  if (!source) throw new Error("the app has not subscribed to the activity stream");
  return source;
}

/** jsdom has no `matchMedia`; this one answers every query alike and can be flipped live. */
function wideScreen(initial: boolean) {
  let matches = initial;
  const listeners = new Set<() => void>();
  vitest.stubGlobal("matchMedia", (media: string) => ({
    get matches() {
      return matches;
    },
    media,
    addEventListener: (_: string, fn: () => void) => listeners.add(fn),
    removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
  }));
  return {
    set(next: boolean) {
      matches = next;
      listeners.forEach((fn) => fn());
    },
  };
}

/** The crew-wide view lives on its own screen now; most of these cases start there. */
async function openManage() {
  await userEvent.click(screen.getByRole("button", { name: /Quản lý/ }));
  return screen.getByTestId("manage-screen");
}

describe("App activity across the crew", () => {
  it("shows a job run arriving over the stream, step by step, until it finishes", async () => {
    backend.agents = [fakeAgent, coachAgent];
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));
    const panel = await openManage();
    expect(panel).toHaveTextContent(vi.noRuns);

    act(() => {
      stream().open();
      stream().emit({ type: "snapshot", runs: [fakeRun({ id: "job1", agent_id: "coach", conversation_id: null, source: "job:coach/brief", status: "running", finished_at: null, spent_usd: 0 })] });
    });
    const card = await within(panel).findByTestId("run-card");
    expect(card).toHaveAttribute("data-status", "running");
    expect(card).toHaveTextContent("HLV sức khoẻ");
    expect(screen.getByRole("button", { name: /Hoạt động/ })).toHaveTextContent("1");

    expect(within(card).getByRole("button", { expanded: true })).toBeInTheDocument();
    act(() => {
      stream().emit({ type: "event", run_id: "job1", agent_id: "coach", conversation_id: null, status: "running", event: { type: "tool_call", tool_call_id: "tc", name: "shell_run", arguments: { command: "date" } } });
    });
    expect(within(card).getByTestId("run-step")).toHaveTextContent("shell_run");
    expect(within(card).getByTestId("run-step")).toHaveTextContent(vi.toolRunning);
    act(() => {
      stream().emit({ type: "event", run_id: "job1", agent_id: "coach", conversation_id: null, status: "running", event: { type: "tool_result", tool_call_id: "tc", name: "shell_run", ok: true, output: "Fri" } });
      stream().emit({ type: "event", run_id: "job1", agent_id: "coach", conversation_id: null, status: "running", event: { type: "assistant_message", message_id: "m", content: "Hôm nay thứ sáu", tool_calls: [], provider: "openrouter", model: "deepseek", cost_usd: 0.001 } });
    });
    expect(within(card).getAllByTestId("run-step")).toHaveLength(2);
    expect(within(card).getAllByTestId("run-step")[0]).toHaveTextContent(vi.toolDone);

    backend.stats = { ...backend.stats, runs: 1, model_calls: 1, spent_usd: 0.001 };
    act(() => {
      stream().emit({ type: "run", run: fakeRun({ id: "job1", agent_id: "coach", conversation_id: null, source: "job:coach/brief", status: "done", spent_usd: 0.001, summary: "Hôm nay thứ sáu" }) });
    });
    expect(within(panel).getByTestId("run-card")).toHaveAttribute("data-status", "done");
    expect(panel).toHaveTextContent(vi.nothingLive);
    // Finishing a run refreshes the bill and the schedule from the server.
    await waitFor(() => expect(backend.requests.filter((r) => r.path === "/stats")).toHaveLength(2));
    await userEvent.click(screen.getByRole("button", { name: vi.costs }));
    expect(screen.getByTestId("stats")).toHaveTextContent("$0.001");
  });

  // The chat has no rail any more, so the count of what is running has to reach the
  // person some other way while they are reading the thread.
  it("counts live runs on the chat's status line and on the way into manage", async () => {
    backend.agents = [fakeAgent, coachAgent];
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));

    act(() => {
      stream().open();
      stream().emit({
        type: "snapshot",
        runs: [
          fakeRun({
            id: "job1",
            agent_id: "coach",
            conversation_id: null,
            source: "job:coach/brief",
            status: "running",
            finished_at: null,
          }),
        ],
      });
    });

    expect(screen.getByTestId("status-line")).toHaveTextContent(`${vi.liveNow}: 1`);
    expect(screen.getByRole("button", { name: /Quản lý/ })).toHaveTextContent("1");
  });

  it("marks stream loss on the status line and lists runs needing attention", async () => {
    backend.runs = [fakeRun({ id: "w", status: "awaiting_approval", conversation_id: "c1", summary: "write_file" })];
    backend.create({ title: "Chờ duyệt", status: "awaiting_approval", messages: [storedMessage("user", "ghi")] });
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));
    act(() => stream().onerror?.());
    expect(screen.getByTestId("status-line")).toHaveTextContent(vi.streamDisconnected);

    await openManage();
    const attention = await screen.findByTestId("attention");
    expect(attention).toHaveTextContent(vi.attentionAwaiting("Agent"));
    // Opening the conversation from here leaves the manage screen for the chat it names.
    await userEvent.click(within(attention).getByRole("button", { name: vi.openConversation }));
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Chờ duyệt");
  });

  it("lists only the master's conversations, creates new ones for it and runs a job now", async () => {
    backend.agents = [fakeAgent, coachAgent];
    backend.jobs = [{ ...coachAgent.schedules[0], id: "coach/brief", schedule_id: "brief", agent_id: "coach", next_run: null, last_run: null, running: false, paused: false }];
    backend.create({ title: "Chung" });
    backend.create({ title: "Sức khoẻ", agent_id: "coach" });
    render(<App />);
    const nav = await screen.findByRole("navigation");
    expect(await within(nav).findByRole("button", { name: /Chung/ })).toBeInTheDocument();
    expect(within(nav).queryByRole("button", { name: /Sức khoẻ/ })).not.toBeInTheDocument();
    expect(within(nav).queryByRole("radiogroup")).not.toBeInTheDocument();
    expect(backend.requests.some((r) => r.path === "/conversations?agent_id=default")).toBe(true);
    expect(within(nav).getByTestId("master-card")).toHaveTextContent("Agent");
    await userEvent.click(within(nav).getByRole("button", { name: `+ ${vi.newConversation}` }));
    await waitFor(() => expect(backend.requests.filter((r) => r.method === "POST" && r.path === "/conversations")[0].body).toEqual({ agent_id: "default" }));
    expect(screen.getByRole("heading", { level: 1 }).parentElement).toHaveTextContent("Agent");

    await openManage();
    await userEvent.click(screen.getByRole("button", { name: vi.jobs }));
    await userEvent.click(screen.getByRole("button", { name: `${vi.runNow}: Bản tin sáng` }));
    await waitFor(() => expect(backend.requests.some((r) => r.method === "POST" && r.path === "/jobs/coach/brief/run")).toBe(true));

    // Pausing goes to the server and the badge reflects the answer it sent back.
    await userEvent.click(screen.getByRole("checkbox", { name: `${vi.jobEnabled}: Bản tin sáng` }));
    await waitFor(() => expect(backend.requests.find((r) => r.method === "PATCH" && r.path === "/jobs/coach/brief/state")?.body).toEqual({ enabled: false }));
    expect(await within(screen.getByTestId("job")).findByText(vi.jobPaused)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: `${vi.jobEnabled}: Bản tin sáng` })).not.toBeChecked();
  });

  it("opens a delegate's conversation from the attention center without listing it", async () => {
    backend.agents = [fakeAgent, coachAgent];
    backend.create({ title: "Chung" });
    const child = backend.create({ title: "Việc của HLV", agent_id: "coach", parent_call_id: "tc1", status: "awaiting_approval", messages: [storedMessage("user", "ghi")] });
    backend.runs = [fakeRun({ id: "w", agent_id: "coach", status: "awaiting_approval", conversation_id: child.id, source: "delegate:c1", summary: "write_file" })];
    render(<App />);
    await screen.findByRole("navigation");
    await openManage();
    const attention = await screen.findByTestId("attention");
    expect(attention).toHaveTextContent(vi.attentionAwaiting("HLV sức khoẻ"));
    await userEvent.click(within(attention).getByRole("button", { name: vi.openConversation }));
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Việc của HLV");
    expect(screen.getByRole("heading", { level: 1 }).parentElement).toHaveTextContent("HLV sức khoẻ");
    const nav = screen.getByRole("navigation");
    expect(within(nav).queryByRole("button", { name: /Việc của HLV/ })).not.toBeInTheDocument();
  });

  it("lists past approval requests with their outcome in the approvals section", async () => {
    backend.agents = [fakeAgent, coachAgent];
    backend.approvals = [
      { id: "ap-old", conversation_id: "c1", message_id: "m", tool_call_id: "tc", tool_name: "write_file", arguments: { path: "x" }, status: "approved", created_at: "2026-09-20T01:00:00Z", expires_at: null, resolved_at: "2026-09-20T01:01:00Z", agent_id: "coach" },
      { id: "ap-exp", conversation_id: "c1", message_id: "m", tool_call_id: "tc2", tool_name: "shell_run", arguments: { command: "rm x" }, status: "expired", created_at: "2026-09-20T00:00:00Z", expires_at: "2026-09-20T00:10:00Z", resolved_at: "2026-09-20T00:10:00Z", agent_id: "default" },
    ];
    backend.create({ title: "Việc" });
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));
    await openManage();
    await userEvent.click(screen.getByRole("button", { name: new RegExp(vi.approvalsTab) }));
    const history = await screen.findByTestId("approval-history");
    const items = within(history).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("HLV sức khoẻ");
    expect(items[0]).toHaveTextContent("write_file");
    expect(items[0]).toHaveTextContent(vi.approvalStatus.approved);
    expect(items[0]).toHaveTextContent("path=x");
    expect(items[1]).toHaveAttribute("data-status", "expired");
    expect(items[1]).toHaveTextContent(vi.approvalStatus.expired);
    await userEvent.click(within(items[0]).getByRole("button", { name: vi.openConversation }));
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Việc");
  });

  // The chat's own strip answers "what was approved here", not "what was approved anywhere".
  it("keeps another conversation's approvals out of the chat's activity strip", async () => {
    const mine = backend.create({ title: "Của tôi" });
    const approval = (id: string, conversationId: string, toolName: string) => ({
      id, conversation_id: conversationId, message_id: "m", tool_call_id: id, tool_name: toolName,
      arguments: {}, status: "approved" as const, created_at: "2026-09-20T01:00:00Z",
      expires_at: null, resolved_at: "2026-09-20T01:01:00Z", agent_id: "default",
    });
    backend.approvals = [approval("a1", mine.id, "write_file"), approval("a2", "other", "shell_run")];
    backend.runs = [fakeRun({ conversation_id: mine.id })];
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Của tôi/ }));

    const strip = await screen.findByTestId("conversation-activity");
    await userEvent.click(within(strip).getByRole("button", { name: vi.conversationActivity.expand }));

    const history = await within(strip).findByTestId("approval-history");
    expect(history).toHaveTextContent("write_file");
    expect(history).not.toHaveTextContent("shell_run");
  });

  it("updates the conversation activity strip when switching between conversations with different runs", async () => {
    const c1 = backend.create({ title: "Conv 1" });
    const c2 = backend.create({ title: "Conv 2" });
    backend.runs = [
      fakeRun({ id: "r1", conversation_id: c1.id, summary: "Work in conv 1" }),
      fakeRun({ id: "r2", conversation_id: c2.id, summary: "Work in conv 2" }),
    ];
    render(<App />);

    // Open first conversation
    await userEvent.click(await screen.findByRole("button", { name: /Conv 1/ }));
    let strip = await screen.findByTestId("conversation-activity");
    await userEvent.click(within(strip).getByRole("button", { name: vi.conversationActivity.expand }));
    expect(within(strip).getByTestId("run-card")).toHaveTextContent("Work in conv 1");
    expect(within(strip).queryByText("Work in conv 2")).not.toBeInTheDocument();

    // Switch to second conversation
    await userEvent.click(screen.getByRole("button", { name: /Conv 2/ }));
    strip = screen.getByTestId("conversation-activity");
    // Switching conversations re-fills the strip; it does not re-collapse it.
    expect(within(strip).getByTestId("run-card")).toHaveTextContent("Work in conv 2");
    expect(within(strip).queryByText("Work in conv 1")).not.toBeInTheDocument();
  });

  it("keeps the activity open beside the chat on a wide screen and folds it under the thread when narrowed", async () => {
    const screenWidth = wideScreen(true);
    const mine = backend.create({ title: "Rộng" });
    backend.runs = [fakeRun({ conversation_id: mine.id, summary: "Việc đã xong" })];
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Rộng/ }));

    const column = await screen.findByTestId("conversation-activity");
    expect(column.closest("main")).toBeNull();
    expect(within(column).getByTestId("run-card")).toHaveTextContent("Việc đã xong");
    expect(within(column).queryByRole("button", { name: vi.conversationActivity.expand })).not.toBeInTheDocument();

    act(() => screenWidth.set(false));

    const strip = screen.getByTestId("conversation-activity");
    expect(strip.closest("main")).not.toBeNull();
    expect(within(strip).getByRole("button", { name: vi.conversationActivity.expand })).toBeInTheDocument();
  });

  it("renders MEDIA lines from the agent workspace as inline images", async () => {
    backend.create({ title: "Ảnh", messages: [storedMessage("assistant", "Biểu đồ:\nMEDIA: out/chart.png")] });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Ảnh/ }));
    const img = await screen.findByRole("img", { name: vi.mediaAlt("out/chart.png") });
    expect(img).toHaveAttribute("src", "/api/agents/default/files?path=out%2Fchart.png");
  });

  it("takes a title the server wrote after the turn into the sidebar, without refetching", async () => {
    // The first sentence named it; the model's better name lands over the stream.
    const conversation = backend.create({ title: "Giúp tôi lập kế hoạch" });
    render(<App />);
    const nav = await screen.findByRole("navigation");
    await userEvent.click(await within(nav).findByRole("button", { name: /Giúp tôi lập kế hoạch/ }));
    const before = backend.requests.filter((r) => r.path.startsWith("/conversations?")).length;

    act(() => {
      stream().open();
      stream().emit({ type: "conversation", conversation: listItem({ ...conversation, title: "Kế hoạch ôn thi" }) });
    });

    expect(within(nav).getByRole("button", { name: /Kế hoạch ôn thi/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Kế hoạch ôn thi");
    expect(backend.requests.filter((r) => r.path.startsWith("/conversations?"))).toHaveLength(before);
  });

  it("ignores a renamed conversation belonging to a delegate, which the sidebar does not list", async () => {
    backend.agents = [fakeAgent, coachAgent];
    backend.create({ title: "Chung" });
    const child = backend.create({ title: "Việc của HLV", agent_id: "coach", parent_call_id: "tc1" });
    render(<App />);
    const nav = await screen.findByRole("navigation");
    await within(nav).findByRole("button", { name: /Chung/ });

    act(() => {
      stream().open();
      stream().emit({ type: "conversation", conversation: listItem({ ...child, title: "Buổi tập tuần này" }) });
    });

    expect(within(nav).queryByRole("button", { name: /Buổi tập tuần này/ })).not.toBeInTheDocument();
  });

  it("leaves the crew's work behind when it goes back to the chat", async () => {
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));

    await openManage();
    await userEvent.click(screen.getByRole("button", { name: vi.manage.backToChat }));

    // The crew's work is a place of its own, so leaving it puts the whole thing away
    // rather than collapsing a strip beside the thread.
    expect(screen.queryByTestId("manage-screen")).not.toBeInTheDocument();
    expect(screen.getByText(vi.welcomeTitleFor("Agent"))).toBeInTheDocument();
  });
});
