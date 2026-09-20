import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi as vitest } from "vitest";
import { App } from "./app";
import { vi } from "./i18n/vi";
import { FakeBackend, storedMessage } from "./test/fake-backend";

let backend: FakeBackend;

beforeEach(() => {
  backend = new FakeBackend();
  vitest.stubGlobal("fetch", backend.fetch);
});

const DENIED_TEXT = "Người dùng đã TỪ CHỐI hành động này.";

describe("App", () => {
  it("shows the welcome screen and echo hint when only the fake provider is configured", async () => {
    render(<App />);
    expect(await screen.findByText(vi.welcomeTitle)).toBeInTheDocument();
    expect(screen.getByText(vi.echoHint)).toBeInTheDocument();
    expect(screen.getByText(vi.noConversations)).toBeInTheDocument();
  });

  it("creates a conversation on first send and renders the streamed reply", async () => {
    backend.nextTurn = [
      { type: "text_delta", text: "Xin " },
      { type: "text_delta", text: "chào" },
      { type: "assistant_message", message_id: "a1", content: "Xin chào", tool_calls: [], provider: "fake", model: "echo", cost_usd: 0 },
      { type: "done", spent_usd: 0.02, unknown_cost_calls: 0 },
    ];
    render(<App />);
    await screen.findByText(vi.welcomeTitle);
    await userEvent.type(screen.getByRole("textbox"), "hello{Enter}");

    expect(await screen.findByTestId("message-assistant")).toHaveTextContent("Xin chào");
    expect(screen.getByTestId("message-user")).toHaveTextContent("hello");
    expect(backend.conversations.size).toBe(1);
    expect(backend.requests.filter((r) => r.path.endsWith("/messages"))[0].body).toEqual({ text: "hello" });
    expect(screen.getByTestId("budget")).toHaveTextContent("$0.02 / $1.00");
    expect(within(screen.getByRole("navigation")).getByRole("button", { current: "page" })).toHaveTextContent(vi.newConversation);
  });

  it("walks the approval flow: pause, approve, then show the tool result", async () => {
    const created = backend.create({ title: "Việc" });
    backend.nextTurn = [
      { type: "assistant_message", message_id: "a1", content: "", tool_calls: [{ id: "tc1", name: "write_file", arguments: { path: "notes.md" } }], provider: null, model: null, cost_usd: null },
      { type: "approval_required", approval_id: "ap1", tool_call_id: "tc1", name: "write_file", arguments: { path: "notes.md" }, reason: "", expires_at: "2026-09-20T03:10:00Z" },
    ];
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Việc/ }));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Việc");
    await userEvent.type(screen.getByRole("textbox"), "ghi chú{Enter}");

    const bar = await screen.findByRole("alertdialog");
    expect(bar).toHaveTextContent(vi.approvalTitle("write_file"));
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByTestId("tool-card")).toHaveTextContent(vi.toolAwaiting);

    backend.nextTurn = [
      { type: "tool_result", tool_call_id: "tc1", name: "write_file", ok: true, output: "đã ghi notes.md" },
      { type: "assistant_message", message_id: "a2", content: "Xong.", tool_calls: [], provider: null, model: null, cost_usd: null },
      { type: "done", spent_usd: 0, unknown_cost_calls: 1 },
    ];
    await userEvent.click(within(bar).getByRole("button", { name: vi.approve }));

    expect(await screen.findByText("Xong.")).toBeInTheDocument();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(screen.getByTestId("tool-card")).toHaveTextContent(vi.toolDone);
    expect(screen.getByRole("textbox")).toBeEnabled();
    expect(screen.getByTitle(vi.unknownCost(1))).toBeInTheDocument();
    const approval = backend.requests.find((r) => r.path.includes("/approvals/"));
    expect(approval).toMatchObject({ path: `/conversations/${created.id}/approvals/ap1`, body: { approve: true } });
  });

  it("restores a stored history including a denied tool and a pending approval", async () => {
    const c = backend.create({
      title: "Cũ",
      status: "awaiting_approval",
      messages: [
        storedMessage("user", "xoá đi"),
        storedMessage("assistant", "", { tool_calls: [{ id: "tc0", name: "write_file", arguments: {} }] }),
        storedMessage("tool", DENIED_TEXT, { tool_call_id: "tc0" }),
        storedMessage("assistant", "", { tool_calls: [{ id: "tc1", name: "write_file", arguments: { path: "b" } }] }),
      ],
      pending_approval: { id: "ap9", conversation_id: "c", message_id: "m", tool_call_id: "tc1", tool_name: "write_file", arguments: { path: "b" }, status: "pending", created_at: "", expires_at: null, resolved_at: null },
    });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Cũ/ }));
    const cards = await screen.findAllByTestId("tool-card");
    expect(cards[0]).toHaveTextContent(vi.toolDenied);
    expect(cards[1]).toHaveTextContent(vi.toolAwaiting);
    expect(screen.getByRole("alertdialog")).toHaveTextContent("path=b");
    expect(backend.requests.some((r) => r.path === `/conversations/${c.id}`)).toBe(true);
  });

  it("always-allows a tool from the approval bar, shows it in the header and revokes it", async () => {
    backend.create({
      title: "Luôn",
      status: "awaiting_approval",
      messages: [storedMessage("assistant", "", { tool_calls: [{ id: "tc1", name: "write_file", arguments: { path: "b" } }] })],
      pending_approval: { id: "ap1", conversation_id: "c1", message_id: "m", tool_call_id: "tc1", tool_name: "write_file", arguments: { path: "b" }, status: "pending", created_at: "", expires_at: "2026-09-20T03:10:00Z", resolved_at: null },
    });
    backend.nextTurn = [
      { type: "tool_result", tool_call_id: "tc1", name: "write_file", ok: true, output: "đã ghi b" },
      { type: "assistant_message", message_id: "a2", content: "Xong.", tool_calls: [], provider: null, model: null, cost_usd: null },
      { type: "done", spent_usd: 0, unknown_cost_calls: 0 },
    ];
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /Luôn/ }));
    const bar = await screen.findByRole("alertdialog");
    expect(bar).toHaveTextContent(/tự từ chối lúc/);
    await userEvent.click(within(bar).getByRole("button", { name: vi.alwaysAllow }));

    expect(await screen.findByText("Xong.")).toBeInTheDocument();
    const approval = backend.requests.find((r) => r.path.includes("/approvals/"));
    expect(approval).toMatchObject({ path: "/conversations/c1/approvals/ap1", body: { approve: true, always: true } });
    const chips = await screen.findByRole("list", { name: vi.autoApproved });
    expect(chips).toHaveTextContent("write_file");

    await userEvent.click(within(chips).getByRole("button", { name: vi.autoApprovedRevoke("write_file") }));
    await waitFor(() => expect(backend.conversations.get("c1")!.auto_approve).toEqual([]));
    expect(screen.queryByRole("list", { name: vi.autoApproved })).not.toBeInTheDocument();
  });

  it("surfaces a halted turn and a 409 conflict as notices", async () => {
    backend.create({ title: "A" });
    backend.nextTurn = [{ type: "halted", reason: "budget", spent_usd: 1 }];
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /^A$/ }));
    await userEvent.type(screen.getByRole("textbox"), "x{Enter}");
    expect(await screen.findByTestId("notice")).toHaveTextContent(vi.haltedBudget);

    backend.conversations.get("c1")!.status = "awaiting_approval";
    await userEvent.type(screen.getByRole("textbox"), "y{Enter}");
    await waitFor(() => expect(screen.getByTestId("notice")).toHaveTextContent(vi.busyConflict));
  });

  it("patches autonomous, skills and title from the header", async () => {
    backend.create({ title: "B" });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /^B$/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: vi.autonomous }));
    await waitFor(() => expect(backend.conversations.get("c1")!.autonomous).toBe(true));

    await userEvent.click(screen.getByText(/Kỹ năng \(0\)/));
    await userEvent.click(screen.getByRole("checkbox", { name: /writer/ }));
    await waitFor(() => expect(backend.conversations.get("c1")!.skills).toEqual(["writer"]));

    vitest.spyOn(window, "prompt").mockReturnValue("Tên mới");
    await userEvent.click(screen.getByRole("button", { name: vi.rename }));
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Tên mới"));
  });

  it("shows the recap of a conversation and rewrites it on demand", async () => {
    backend.create({ title: "C", summary: "Bản tóm tắt cũ." });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /^C/ }));
    expect(screen.getAllByText("Bản tóm tắt cũ.").length).toBeGreaterThan(0);

    await userEvent.click(screen.getByRole("button", { name: vi.resummarize }));
    expect(await screen.findAllByText(backend.nextSummary)).toHaveLength(2);
    expect(backend.conversations.get("c1")!.summary).toBe(backend.nextSummary);
    expect(backend.requests.some((r) => r.method === "POST" && r.path === "/conversations/c1/summary")).toBe(true);
  });

  it("says a conversation has no recap yet when none was written", async () => {
    backend.create({ title: "D" });
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /^D$/ }));
    expect(screen.getByText(vi.noSummary)).toBeInTheDocument();
  });

  it("deletes after confirmation and opens the settings drawer without secrets", async () => {
    backend.create({ title: "Xoá tôi" });
    render(<App />);
    await screen.findByRole("button", { name: /Xoá tôi/ });
    vitest.spyOn(window, "confirm").mockReturnValue(true);
    await userEvent.click(screen.getByRole("button", { name: vi.deleteConversation }));
    expect(await screen.findByText(vi.noConversations)).toBeInTheDocument();
    expect(backend.conversations.size).toBe(0);

    await userEvent.click(screen.getByRole("button", { name: /Cài đặt/ }));
    const drawer = screen.getByRole("dialog");
    expect(drawer).toHaveTextContent("fake:echo");
    expect(drawer).toHaveTextContent(vi.keyMissing);
    expect(drawer).toHaveTextContent(vi.requiresApproval);
    expect(drawer).toHaveTextContent("/tmp/home/workspace");
    await userEvent.click(within(drawer).getByRole("button", { name: vi.close }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows the shared user directory in settings", async () => {
    render(<App />);
    await screen.findByText(vi.welcomeTitle);
    await userEvent.click(screen.getByRole("button", { name: /Cài đặt/ }));
    expect(screen.getByRole("dialog")).toHaveTextContent("/tmp/home/users");
  });

  it("opens the memory tab and counts the proposals waiting for a decision", async () => {
    backend.addProposal({ description: "Ngủ trước 23h" });
    render(<App />);
    await screen.findByText(vi.welcomeTitle);

    const tab = await screen.findByRole("tab", { name: new RegExp(vi.memory.tab) });
    await waitFor(() => expect(tab).toHaveTextContent("1"));

    await userEvent.click(tab);
    expect(await screen.findByTestId("memory-panel")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: new RegExp(vi.memory.proposals) }));
    expect(await screen.findByText("Ngủ trước 23h")).toBeInTheDocument();
  });
});
