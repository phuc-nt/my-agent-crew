import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, FakeEventSource, coachAgent, fakeAgent, fakeRun, storedMessage } from "./test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  FakeEventSource.instances = [];
  vitest.stubGlobal("fetch", backend.fetch);
  vitest.stubGlobal("EventSource", FakeEventSource);
});

function stream(): FakeEventSource {
  const source = FakeEventSource.instances.at(-1);
  if (!source) throw new Error("the app has not subscribed to the activity stream");
  return source;
}

describe("App activity rail", () => {
  it("shows a job run arriving over the stream, step by step, until it finishes", async () => {
    backend.agents = [fakeAgent, coachAgent];
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));
    const panel = screen.getByTestId("activity-panel");
    expect(panel).toHaveTextContent(vi.noRuns);

    act(() => {
      stream().open();
      stream().emit({ type: "snapshot", runs: [fakeRun({ id: "job1", agent_id: "coach", conversation_id: null, source: "job:coach/brief", status: "running", finished_at: null, spent_usd: 0 })] });
    });
    const card = await within(panel).findByTestId("run-card");
    expect(card).toHaveAttribute("data-status", "running");
    expect(card).toHaveTextContent("HLV sức khoẻ");
    expect(screen.getByTestId("status-line")).toHaveTextContent(`${vi.liveNow}: 1`);
    expect(screen.getByRole("button", { name: /Hoạt động/, pressed: true })).toHaveTextContent("1");

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
    await userEvent.click(screen.getByRole("tab", { name: vi.costs }));
    expect(screen.getByTestId("stats")).toHaveTextContent("$0.001");
  });

  it("marks stream loss on the status line and lists runs needing attention", async () => {
    backend.runs = [fakeRun({ id: "w", status: "awaiting_approval", conversation_id: "c1", summary: "write_file" })];
    backend.create({ title: "Chờ duyệt", status: "awaiting_approval", messages: [storedMessage("user", "ghi")] });
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));
    const attention = await screen.findByTestId("attention");
    expect(attention).toHaveTextContent(vi.attentionAwaiting("Agent"));
    act(() => stream().onerror?.());
    expect(screen.getByTestId("status-line")).toHaveTextContent(vi.streamDisconnected);
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

    await userEvent.click(screen.getByRole("tab", { name: vi.jobs }));
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
    const attention = await screen.findByTestId("attention");
    expect(attention).toHaveTextContent(vi.attentionAwaiting("HLV sức khoẻ"));
    await userEvent.click(within(attention).getByRole("button", { name: vi.openConversation }));
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("Việc của HLV");
    expect(screen.getByRole("heading", { level: 1 }).parentElement).toHaveTextContent("HLV sức khoẻ");
    const nav = screen.getByRole("navigation");
    expect(within(nav).queryByRole("button", { name: /Việc của HLV/ })).not.toBeInTheDocument();
  });

  it("lists past approval requests with their outcome in the approvals tab", async () => {
    backend.agents = [fakeAgent, coachAgent];
    backend.approvals = [
      { id: "ap-old", conversation_id: "c1", message_id: "m", tool_call_id: "tc", tool_name: "write_file", arguments: { path: "x" }, status: "approved", created_at: "2026-09-20T01:00:00Z", expires_at: null, resolved_at: "2026-09-20T01:01:00Z", agent_id: "coach" },
      { id: "ap-exp", conversation_id: "c1", message_id: "m", tool_call_id: "tc2", tool_name: "shell_run", arguments: { command: "rm x" }, status: "expired", created_at: "2026-09-20T00:00:00Z", expires_at: "2026-09-20T00:10:00Z", resolved_at: "2026-09-20T00:10:00Z", agent_id: "default" },
    ];
    backend.create({ title: "Việc" });
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));
    await userEvent.click(screen.getByRole("tab", { name: vi.approvalsTab }));
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

  it("renders MEDIA lines from the agent workspace as inline images", async () => {
    backend.create({ title: "Ảnh", messages: [storedMessage("assistant", "Biểu đồ:\nMEDIA: out/chart.png")] });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Ảnh/ }));
    const img = await screen.findByRole("img", { name: vi.mediaAlt("out/chart.png") });
    expect(img).toHaveAttribute("src", "/api/agents/default/files?path=out%2Fchart.png");
  });

  it("can hide the activity rail", async () => {
    render(<App />);
    await screen.findByText(vi.welcomeTitleFor("Agent"));
    await userEvent.click(screen.getByRole("button", { name: /Hoạt động/ }));
    expect(screen.queryByTestId("activity-panel")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Hoạt động/ })).toHaveAttribute("aria-pressed", "false");
  });
});
